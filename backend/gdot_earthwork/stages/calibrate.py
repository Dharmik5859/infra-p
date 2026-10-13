"""Stage 3 -- calibrate: feet per grid square on each axis, and the centreline.

A cross-section's grid is usually 10 ft a square both ways, but not always:
1"=20' sheets may grid at 20 ft, and some plot the vertical exaggerated
(5 ft or 2 ft a square up, 10 ft across). The axes say which: the offset
labels under the section step by the horizontal size of a square, the
elevation labels beside it by the vertical one. This stage reads them:

  horizontal  offset labels from the text layer, fit to
              v = step * (line - centre line)  (or |v| = step * |..| where the
              left side is printed unsigned); on a scan, the labels' widths
              (where they turn from two digits to three), confirmed by OCR of
              the widest labels when they point away from the standard grid
  vertical    elevation labels on the major horizontal lines, left or right
              of the frame (text layer, else OCR), fit to
              elev = top - step * row

A step is accepted only when at least three labels agree on it, nearly all
of what was read fits it, and it is a step drawings use; otherwise the axis
keeps the configured grid (cfg.grid_ft) and says it was assumed. Scans are
read once per page per frame layout (sections of one sheet share axes).
"""
from __future__ import annotations

import re
import shutil
from collections import Counter
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import PipelineConfig
from ..frames import (_AXIS_NUM_RE, Frame, _clean_for_ocr, _glyph_only, _ocr_number, _tesseract, _vline_index,
                      _word_boxes, axis_label_words, find_centreline, width_fits)
from ..pages import PageImage

PLAUSIBLE_FT = (1.0, 2.0, 2.5, 4.0, 5.0, 10.0, 20.0, 25.0, 40.0, 50.0, 100.0)
_ELEV_RE = re.compile(r"^(\d{1,5})(?:\.(\d{1,2}))?$")


@dataclass
class FrameScale:
    ft_x: float                    # ft per major grid square, horizontal
    ft_y: float                    # ... vertical
    source_x: str                  # "labels" (text layer), "label_widths" / "ocr" (scan) or "assumed"
    source_y: str
    px_per_ft_x: float             # page-image pixels per ft
    px_per_ft_y: float
    centre_x: float | None         # image x of offset 0, None when unread
    centre_source: str | None      # "text" / "scan" (see frames.find_centreline)
    labels_x: int = 0              # labels that fit the horizontal step
    labels_y: int = 0

    def as_dict(self) -> dict:
        return {"ftPerSquareX": self.ft_x, "ftPerSquareY": self.ft_y, "sourceX": self.source_x,
                "sourceY": self.source_y, "pixelsPerFootX": round(self.px_per_ft_x, 6),
                "pixelsPerFootY": round(self.px_per_ft_y, 6), "labelsX": self.labels_x, "labelsY": self.labels_y,
                "verticalDiffers": abs(self.ft_x - self.ft_y) > 1e-9}


# ------------------------------------------------------------------ fitting

def fit_offset_step(reads: list[tuple[int, int]], n_lines: int, signed: bool) -> tuple[float, int] | None:
    """(ft per square, labels fitting) from offset-axis reads (line, value).
    `signed`: the sheet prints the left side negative (else unsigned, or the
    sign was not read). Each candidate step and centre line predicts every
    label; the step explaining the most wins, if clearly and with three or more."""
    if len(reads) < 3:
        return None
    best: dict[float, int] = {}
    for step in PLAUSIBLE_FT:
        for k0 in range(n_lines):
            if signed:
                n = sum(v == step * (k - k0) for k, v in reads)
            else:
                n = sum(abs(v) == step * abs(k - k0) for k, v in reads)
            best[step] = max(best.get(step, 0), n)
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    (step, n), (_, n2) = ranked[0], ranked[1]
    if n < 3 or n < 0.8 * len(reads) or n2 >= n:
        return None
    return step, n


def fit_elevation_step(reads: list[tuple[float, float]]) -> tuple[float, int] | None:
    """(ft per square, labels fitting) from elevation reads (row in grid
    squares from the top, value). Elevations fall by `step` per square."""
    if len(reads) < 3:
        return None
    scored = []
    for step in PLAUSIBLE_FT:
        tops = Counter(round(v + step * j, 2) for j, v in reads)
        top, n = tops.most_common(1)[0]
        scored.append((n, step))
    scored.sort(reverse=True)
    n, step = scored[0]
    if n < 3 or n < 0.8 * len(reads) or (len(scored) > 1 and scored[1][0] >= n):
        return None
    return step, n


# ------------------------------------------------------------------ reading

def _offset_reads_text(frame: Frame, img: PageImage) -> list[tuple[int, int]]:
    lo, hi = frame.bottom - 0.5 * frame.pitch_y, frame.bottom + 0.6 * frame.pitch_y
    reads = []
    for sp in img.spans:
        t = sp.text.strip()
        if _AXIS_NUM_RE.match(t) and lo <= sp.y <= hi \
                and frame.left - 0.3 * frame.pitch_x <= sp.x <= frame.right + 0.3 * frame.pitch_x:
            k = _vline_index(frame, sp.x)
            if k is not None:
                reads.append((k, int(t)))
    return reads


def _elevation_reads_text(frame: Frame, img: PageImage) -> list[tuple[float, float]]:
    """Numbers left or right of the frame sitting on a major horizontal line."""
    reads, seen = [], set()
    for sp in img.spans:
        m = _ELEV_RE.match(sp.text.strip())
        if not m:
            continue
        beside = frame.left - 1.6 * frame.pitch_x <= sp.x < frame.left - 0.05 * frame.pitch_x \
            or frame.right + 0.05 * frame.pitch_x < sp.x <= frame.right + 1.6 * frame.pitch_x
        if not beside or not frame.top - 0.3 * frame.pitch_y <= sp.y <= frame.bottom + 0.3 * frame.pitch_y:
            continue
        j = (sp.y - frame.top) / frame.pitch_y
        if abs(j - round(j)) > 0.25:
            continue
        if round(j) in seen:              # labelled on both sides: count each row once
            continue
        seen.add(round(j))
        reads.append((float(round(j)), float(sp.text)))
    return reads


def offset_step_from_widths(frame: Frame, img: PageImage, cfg: PipelineConfig) -> float | None:
    """The horizontal step of a scanned section from its offset labels'
    widths: where the labels turn from two digits to three says how many
    squares make 100 ft. Each plausible step is fitted (frames.width_fits);
    one clearly better than every other wins. Widths alone only CONFIRM the
    standard grid: a different step must also be read by OCR on the widest
    labels (two or more agreeing with it, and more agreeing than not) --
    widths are easily fooled by labels that run together on a scan."""
    words, glyphs = axis_label_words(frame, img, cfg.ink_thresh)
    widths = {line: box[2] for line, box, _ in words}
    scored = []
    for step in (5.0, 10.0, 20.0, 25.0, 50.0):
        fits = width_fits(frame, widths, step)
        if fits:
            scored.append((fits[0][0], step, fits[0][1]))
    scored.sort()
    if not scored or scored[0][0] > 0.25 or (len(scored) > 1 and scored[1][0] < 1.6 * scored[0][0]):
        return None
    _, step, k0 = scored[0]
    if step == cfg.grid_ft:
        return step
    agree = disagree = 0
    for line, box, _ in sorted(words, key=lambda w: -w[1][2])[:6]:
        got = _ocr_number(glyphs, box, frame.pitch_y)
        if got:
            if got[0] == step * abs(line - k0):
                agree += 1
            else:
                disagree += 1
    return step if agree >= 2 and agree > disagree else None


def _ocr_elevation(clean: np.ndarray, box, pitch: float) -> float | None:
    word = _glyph_only(clean, box, pitch, int(0.1 * pitch))
    x, y, w, h = box
    reads = []
    for height in (40, 64):
        f = height / max(1, h)
        im = cv2.resize(word, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        im = cv2.copyMakeBorder(im, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        m = _ELEV_RE.match(_tesseract(im, "7").strip().replace("+", ""))
        if not m:
            return None
        reads.append(float(m.group(0)))
    return reads[0] if reads[0] == reads[1] else None


def _elevation_reads_scan(frame: Frame, img: PageImage, cfg: PipelineConfig) -> list[tuple[float, float]]:
    H, W = img.gray.shape
    p = frame.pitch_y
    for x0, x1 in ((frame.left - 1.6 * frame.pitch_x, frame.left - 2),
                   (frame.right + 2, frame.right + 1.6 * frame.pitch_x)):
        x0, x1 = max(0, int(x0)), min(W, int(x1))
        y0, y1 = max(0, int(frame.top - 0.4 * p)), min(H, int(frame.bottom + 0.4 * p))
        if x1 - x0 < 0.3 * frame.pitch_x or y1 <= y0:
            continue
        # outside the grid: any long rule (a border) is removed by the cleaning
        clean = _clean_for_ocr(img.gray[y0:y1, x0:x1].copy(), cfg.ink_thresh)
        reads = []
        for box in _word_boxes((clean < 128).astype(np.uint8), p):
            j = (y0 + box[1] + box[3] / 2 - frame.top) / p
            if abs(j - round(j)) > 0.3 or box[2] < 0.15 * p:
                continue
            v = _ocr_elevation(clean, box, p)
            if v is not None:
                reads.append((float(round(j)), v))
            if len(reads) >= 5:
                break
        if len(reads) >= 3:
            return reads
    return []


# ------------------------------------------------------------------ stage

def calibrate(frame: Frame, img: PageImage, cfg: PipelineConfig, page_cache: dict | None = None) -> FrameScale:
    """Read the frame's scale on both axes and its centreline. Sets
    frame.ft_x / frame.ft_y (what tracing resamples with) and returns the
    full reading. `page_cache` (one dict per page) shares a scan's reading
    between sections of the same layout."""
    ft_x = ft_y = cfg.grid_ft
    src_x = src_y = "assumed"
    n_x = n_y = 0
    key = (round(frame.pitch_x), round(frame.pitch_y), len(frame.vlines))
    cached = page_cache.get(key) if page_cache is not None else None
    if img.spans:
        reads = _offset_reads_text(frame, img)
        got = fit_offset_step(reads, len(frame.vlines), any(v < 0 for _, v in reads))
        if got:
            (ft_x, n_x), src_x = got, "labels"
        got = fit_elevation_step(_elevation_reads_text(frame, img))
        if got:
            (ft_y, n_y), src_y = got, "labels"
    if (img.kind == "raster" or not img.spans) and shutil.which("tesseract"):
        if cached is not None:
            (ft_x, src_x, n_x), (ft_y, src_y, n_y) = cached
        else:
            if src_x == "assumed":
                step = offset_step_from_widths(frame, img, cfg)
                if step:
                    ft_x, src_x = step, "label_widths"
            if src_y == "assumed":
                got = fit_elevation_step(_elevation_reads_scan(frame, img, cfg))
                if got and (got[0] == cfg.grid_ft or got[1] >= 4):
                    (ft_y, n_y), src_y = got, "ocr"
            if page_cache is not None:
                page_cache[key] = ((ft_x, src_x, n_x), (ft_y, src_y, n_y))
    if src_y == "assumed" and src_x != "assumed":
        ft_y = ft_x                      # sections are drawn undistorted unless the labels say otherwise
    frame.ft_x, frame.ft_y = float(ft_x), float(ft_y)
    centre = find_centreline(frame, img, cfg.ink_thresh, frame.ft_x)
    return FrameScale(ft_x=frame.ft_x, ft_y=frame.ft_y, source_x=src_x, source_y=src_y,
                      px_per_ft_x=frame.pitch_x / frame.ft_x, px_per_ft_y=frame.pitch_y / frame.ft_y,
                      centre_x=centre[0] if centre else None, centre_source=centre[1] if centre else None,
                      labels_x=n_x, labels_y=n_y)


def centre_ft(frame: Frame, scale: FrameScale) -> float | None:
    """The centreline as ft from the frame's left grid line."""
    if scale.centre_x is None:
        return None
    return round((scale.centre_x - frame.left) / scale.px_per_ft_x, 2)
