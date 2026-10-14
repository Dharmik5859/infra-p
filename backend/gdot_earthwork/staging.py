"""
Staged-construction sheets: measure only the sheet's own stage.

A construction-staging sheet ("STAGE 3" in its title block) draws the whole
section, but marks the stretches built in other stages with a dimension line
labelled "STAGE 2 CONSTRUCTION" (lighter linework underneath). The takeoff for
that sheet is its own stage's share, so those stretches are left out. A
"STAGE n CONSTRUCTION" mark for the sheet's own stage changes nothing.

    sheet_stage(img, hint)        the sheet's stage: its title block, else the
                                  file name ("... - STAGE 3.pdf"), else None
    stage_spans(frame, img, cfg)  [(stage, x_from, x_to, y)] in page-image
                                  pixels, one per "STAGE n CONSTRUCTION" dimension
    other_stage(a, b)             True only when the stage NUMBERS differ
                                  (OCR may drop the letter of "1A")

Only plan sets whose file name or sheet title names a stage are read this way,
so mainline sheets are untouched.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

import cv2
import numpy as np

from .config import PipelineConfig
from .frames import Frame
from .pages import PageImage

_STAGE_RE = re.compile(r"STAGE\s*[-_ ]*\s*(\d+[A-Z]?)\b", re.I)


def stage_from_name(name: str | None) -> str | None:
    m = _STAGE_RE.search(name or "")
    return m.group(1).upper() if m else None


def _norm(tok: str) -> str | None:
    t = re.sub(r"[^0-9A-Za-z]", "", tok).upper()
    m = re.match(r"^(\d{1,2})([A-Z]?)$", t)
    return (m.group(1) + m.group(2)) if m else None


def other_stage(a: str | None, b: str | None) -> bool:
    """Whether stage `a` is a different stage from `b`. Compared by number
    only: "1" and "1A" are taken as the same, since OCR may drop the letter --
    a stretch is left out only when it is surely another stage."""
    if not a or not b:
        return False
    na, nb = re.match(r"\d+", a), re.match(r"\d+", b)
    return bool(na and nb) and na.group(0) != nb.group(0)


def _ocr_words(gray: np.ndarray, scale: float) -> list[tuple[str, int, int, int, int]]:
    """Words with boxes (x, y, w, h) in `gray`'s pixels."""
    if not shutil.which("tesseract") or gray.size == 0:
        return []
    im = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", im)
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11", "tsv"], input=buf.tobytes(),
                       capture_output=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"}, timeout=120)
    out = []
    for line in r.stdout.decode("utf-8", "ignore").splitlines()[1:]:
        c = line.split("\t")
        if len(c) == 12 and c[11].strip():
            x, y, w, h = (int(int(v) / scale) for v in c[6:10])
            out.append((c[11].strip(), x, y, w, h))
    return out


def _words(img: PageImage, x0: int, y0: int, x1: int, y1: int, scale: float = 0.5):
    """Words in a page-image rectangle, from the text layer when there is one."""
    if img.spans:
        out = []
        for sp in img.spans:
            text = sp.text.strip()
            if not text or not (x0 <= sp.x <= x1 and y0 <= sp.y <= y1):
                continue
            cw = 0.6 * sp.size                       # a character's width, roughly
            left = sp.x - len(text) * cw / 2         # spans are placed by their centre
            for m in re.finditer(r"\S+", text):
                out.append((m.group(0), int(left + m.start() * cw), int(sp.y - sp.size / 2),
                            int(len(m.group(0)) * cw), int(sp.size)))
        return out
    crop = img.gray[y0:y1, x0:x1]
    # read twice: as scanned, and with long lines whited out (a dimension line
    # running through a label garbles it); stage_spans merges what both found
    return [(t, x + x0, y + y0, w, h) for g in (crop, _without_rules(crop)) for t, x, y, w, h in _ocr_words(g, scale)]


def _without_rules(gray: np.ndarray, run: int = 60) -> np.ndarray:
    """The image with long straight lines (dimension lines, grid, extension
    lines) whited out, so a label a line runs through can still be read."""
    ink = (gray < 200).astype(np.uint8)
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (run, 1))) | \
        cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, run)))
    out = gray.copy()
    out[cv2.dilate(lines, np.ones((3, 3), np.uint8)) > 0] = 255
    return out


def _stages_in(words) -> list[tuple[str, tuple[int, int, int, int]]]:
    """("STAGE", id) pairs among words, with the box of the whole label."""
    out = []
    flat = []
    for t, x, y, w, h in words:
        for part in t.split():
            part = re.sub(r"^[^0-9A-Za-z]+|[^0-9A-Za-z]+$", "", part)    # OCR'd quotes, bars, dots
            if part:
                flat.append((part, x, y, w, h))
    for i, (t, x, y, w, h) in enumerate(flat):
        if not re.match(r"^STAGE\b", t, re.I):
            continue
        inline = re.match(r"^STAGE[-_ ]*(\d{1,2}[A-Z]?)$", t, re.I)
        sid = inline.group(1).upper() if inline else None
        box = [x, y, x + w, y + h]
        for t2, x2, y2, w2, h2 in flat[i + 1:i + 3]:
            same_line = abs((y2 + h2 / 2) - (y + h / 2)) < 0.6 * h and 0 <= x2 - (x + w) < 3 * h
            if sid is None and same_line and _norm(t2):
                sid = _norm(t2)
                box = [min(box[0], x2), min(box[1], y2), max(box[2], x2 + w2), max(box[3], y2 + h2)]
            elif sid is not None and re.match(r"^CONSTRUC", t2, re.I):
                box = [min(box[0], x2), min(box[1], y2), max(box[2], x2 + w2), max(box[3], y2 + h2)]
        if sid:
            out.append((sid, tuple(box)))
    return out


def sheet_stage(img: PageImage, hint: str | None = None) -> str | None:
    """The stage a sheet shows: from the title block (bottom right of the
    sheet), else from the file name."""
    H, W = img.gray.shape
    for sid, _ in _stages_in(_words(img, int(W * 0.6), int(H * 0.78), W, H)):
        return sid
    return stage_from_name(hint)


def stage_spans(frame: Frame, img: PageImage, cfg: PipelineConfig) -> list[tuple[str, float, float, float]]:
    """Each "STAGE n CONSTRUCTION" mark in the section, with the stretch its
    dimension line spans: [(stage, x_from, x_to, y)] in page-image pixels
    (y: the dimension line's row, so it can be kept out of the tracing)."""
    x0, x1 = frame.left, frame.right
    y0, y1 = frame.y0, frame.y1
    labels = []
    for sid, box in _stages_in(_words(img, x0, y0, x1, y1)):      # each label once, though read twice
        if not any(o[0] == sid and box[0] < o[1][2] and o[1][0] < box[2] and box[1] < o[1][3] and o[1][1] < box[3]
                   for o in labels):
            labels.append((sid, box))
    if not labels:
        return []
    # dimension lines are drawn thin: look for them at a lighter threshold than the linework
    ink = (img.gray[y0:y1, x0:x1] < max(cfg.ink_thresh, 235)).astype(np.uint8)
    for a, b in frame.hlines:                                   # the grid is not a dimension line
        ink[max(0, a - y0 - 1):max(0, b - y0 + 2), :] = 0
    ft = frame.pitch_x / frame.ft_x                             # pixels per ft across
    run = max(5, int(2 * ft))
    rows = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (run, 1)))
    out = []
    for sid, (bx0, by0, bx1, by1) in labels:
        bx0, bx1, by0, by1 = bx0 - x0, bx1 - x0, by0 - y0, by1 - y0
        h = max(4, by1 - by0)
        lo, hi = max(0, int(by0 - 1.2 * frame.pitch_y)), min(ink.shape[0], int(by1 + 0.4 * frame.pitch_y))
        best = None
        for r in range(lo, hi):
            xs = np.where(rows[r])[0]
            if not len(xs):
                continue
            # runs on this row; a dimension line may be broken by its own label
            breaks = np.where(np.diff(xs) > max(run, (bx1 - bx0) + 2 * ft))[0]
            for seg in np.split(xs, breaks + 1):
                a, b = int(seg[0]), int(seg[-1])
                near = a - 1.5 * ft <= bx1 and b + 1.5 * ft >= bx0         # touches the label's columns
                close = r >= by0 - 1.2 * frame.pitch_y and r <= by1 + 2 * h
                if not (near and close and b - a >= 3 * ft):
                    continue
                # the label's own line is the one right under (or over) it; another
                # dimension nearby (a lane width) may be longer, but sits further off
                gap = 0 if by0 <= r <= by1 else min(abs(r - by0), abs(r - by1))
                key = (round(gap / h), -(b - a))
                if best is None or key < best[3]:
                    best = (a, b, r, key)
        if best:
            out.append((sid, x0 + best[0], x0 + best[1], y0 + best[2]))
    return out

