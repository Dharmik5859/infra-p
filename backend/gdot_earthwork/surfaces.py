"""
Extract the two surfaces of one cross-section -- EXISTING GROUND (dashed)
and PROPOSED DESIGN (solid) -- and measure the fill/cut area between them.

Two extractors produce the same `Surfaces` result:

* raster_surfaces(): for scanned sheets. Works from pixels.
* vector_surfaces(): for CAD-exported PDFs. Reads the drawing's own stroke
  geometry, so dashed vs solid, text vs line and grid vs data are known
  exactly instead of guessed from pixels.

Both resample the frame to a CANONICAL resolution (CANON_PPF pixels per
foot, the same on both axes) before tracing. Scans arrive at 14.4 px/ft
(19 series), 18 px/ft (23 series) or anything else; normalising once
means every pixel constant in tracing.py means the same thing on every
sheet, and vertical exaggeration (different horizontal and vertical
scales) is undone for free.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import PipelineConfig
from .frames import Frame
from .pages import PageImage
from .tracing import (
    best_path, candidates, denoise, densify, despike, drop_structures, fill_along_gridlines,
    drop_rulers, ground_candidates, interp_spans, snap_bottom,
    refine_gaps, snap_top, split_chain, split_dash_solid, strip_grid, template_strokes,
    trim_buried_tail,
)

CANON_PPF = 14.4   # px per ft the tracing constants were tuned at (19-series native)

# How far (canonical px) the surface tracer may jump across a gap. Existing
# ground routinely disappears for 50-100 ft where it runs underneath a
# thick proposed-design line (mill & overlay, widening); the tracer must
# bridge that rather than keep only the longer half of the ground.
TRACE_WINDOW = int(110 * CANON_PPF)

# Template strokes closer than this belong to one network; isolated solid
# pieces narrower than MIN_TEMPLATE_PX are annotation (leaders, callouts).
LINK_PX = int(2.0 * CANON_PPF)

# Reward for the ground tracer following a template stroke instead of its own
# dashes (see tracing.ground_candidates).
HIDDEN_GROUND_WEIGHT = 1 / 3
MIN_TEMPLATE_PX = int(15 * CANON_PPF)


@dataclass
class Surfaces:
    ground: np.ndarray          # row (canonical px, frame-local) per column, NaN = absent
    design: np.ndarray          # finished grade (top of the template)
    width: int                  # canonical columns
    height: int                 # canonical rows
    source: str                 # "raster" or "vector"
    roi: np.ndarray | None = None          # cleaned ink mask, for overlays
    max_gap_ground_ft: float = 0.0
    max_gap_design_ft: float = 0.0
    trimmed: list[dict] = field(default_factory=list)
    structures: list[dict] = field(default_factory=list)   # design spans dropped as bridges
    subgrade: np.ndarray | None = None     # bottom of the pavement structure (= design elsewhere)

    def surface(self, which: str) -> np.ndarray:
        if which == "subgrade" and self.subgrade is not None:
            return self.subgrade
        return self.design

    @property
    def overlap(self) -> np.ndarray:
        return ~np.isnan(self.ground) & ~np.isnan(self.design)

    def x_ft(self, col) -> np.ndarray:
        """Horizontal offset of a column from the frame centre, in ft."""
        return (np.asarray(col, float) - self.width / 2) / CANON_PPF


@dataclass
class Area:
    fill_ft2: float
    cut_ft2: float

    @property
    def net_ft2(self) -> float:
        return self.fill_ft2 - self.cut_ft2


def measure(s: Surfaces, surface: str = "subgrade") -> Area:
    """Fill where the proposed surface sits above existing ground (smaller row
    = higher), cut where it sits below. `surface`: "subgrade" (bottom of the
    pavement structure -- the usual earthwork convention) or "finished"
    (finished grade). Columns are 1/CANON_PPF ft wide and the curves are
    piecewise linear per column, so a column sum is exact to the raster."""
    top = s.surface(surface)
    ov = ~np.isnan(s.ground) & ~np.isnan(top)
    if not ov.any():
        return Area(0.0, 0.0)
    d = (s.ground[ov] - top[ov]) / CANON_PPF        # ft, +ve = fill
    col_ft = 1.0 / CANON_PPF
    return Area(float(d[d > 0].sum() * col_ft), float(-d[d < 0].sum() * col_ft))


# Design lines are solid: a stretch with no ink this long is a real break
# (bridge end, drawing break), not a dash gap, and is never bridged.
DESIGN_SPLIT_FT = 5.0


# How far below finished grade the subgrade (bottom of the pavement box) may
# lie. Pavement sections and curbs are 1-3 ft deep.
SUBGRADE_REACH_FT = 3.5


def _finish(ground_px: dict, design_px: dict, solid: np.ndarray, roi: np.ndarray,
            W: int, H: int, cfg: PipelineConfig, source: str, refine: bool) -> Surfaces:
    if refine:
        ground_px, _ = refine_gaps(ground_px, roi, CANON_PPF, cfg.gap_refine_ft, cfg.gap_tol_px)
        design_px, _ = refine_gaps(design_px, solid, CANON_PPF, cfg.gap_refine_ft, cfg.gap_tol_px)
    _, gap_g = interp_spans(ground_px, W, CANON_PPF, cfg.gap_warn_ft)
    G, _ = despike(densify(ground_px, W), cfg.despike_win, cfg.despike_px)

    pieces = split_chain(design_px, int(DESIGN_SPLIT_FT * CANON_PPF))
    pieces, structures = drop_structures(pieces, G, CANON_PPF)
    D = np.full(W, np.nan)
    B = np.full(W, np.nan)
    gap_d = 0.0
    reach = int(SUBGRADE_REACH_FT * CANON_PPF)
    for pc in pieces:
        for arr, chain in ((D, pc), (B, snap_bottom(solid, pc, reach))):
            dense = densify(chain, W)
            ok = ~np.isnan(dense)
            arr[ok] = dense[ok]
        gap_d = max(gap_d, interp_spans(pc, W, CANON_PPF, cfg.gap_warn_ft)[1])
    D, _ = despike(D, cfg.despike_win, cfg.despike_px)
    B, _ = despike(B, cfg.despike_win, cfg.despike_px)
    x = (np.arange(W) - W / 2) / CANON_PPF
    D, trimmed = trim_buried_tail(x, G, D, CANON_PPF, cfg.buried_run_ft, cfg.buried_depth_ft)
    B[np.isnan(D)] = np.nan
    s = Surfaces(G, D, W, H, source, roi, gap_g, gap_d, trimmed)
    s.subgrade = B
    s.structures = [dict(x_from=round(float(x[n["x_from"]]), 1), x_to=round(float(x[n["x_to"]]), 1))
                    for n in structures]
    return s


def _canon_size(frame: Frame, cfg: PipelineConfig) -> tuple[float, float, int, int]:
    sx = CANON_PPF / (frame.pitch_x / cfg.grid_ft)
    sy = CANON_PPF / (frame.pitch_y / cfg.grid_ft)
    W = int(round((frame.right - frame.left + 1) * sx))
    H = int(round((frame.y1 - frame.y0 + 1) * sy))
    return sx, sy, W, H


# ------------------------------------------------------------------ raster

def raster_surfaces(frame: Frame, img: PageImage, cfg: PipelineConfig) -> Surfaces:
    x0, x1, y0, y1 = frame.left, frame.right + 1, frame.y0, frame.y1 + 1
    gray = img.gray[y0:y1, x0:x1]
    ink = (gray < cfg.ink_thresh).astype(np.uint8)
    # Grid lines are removed at native resolution, where their positions are
    # known to the pixel, then the cleaned mask is resampled.
    V = [(a - x0, b - x0) for a, b in frame.vlines]
    Hh = [(a - y0, b - y0) for a, b in frame.hlines]
    V += _partial_grid_lines(ink, V, frame.pitch_x, axis=1)
    Hh += _partial_grid_lines(ink, Hh, frame.pitch_y, axis=0)
    clean = strip_grid(ink, V, Hh, sliver=int(0.8 * min(frame.pitch_x, frame.pitch_y)))
    sx, sy, W, H = _canon_size(frame, cfg)
    canon = cv2.resize(clean.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA)
    roi = (canon > 0.25).astype(np.uint8)
    # blank the outermost band: frame border, axis ticks
    m = 3
    roi[:m], roi[-m:], roi[:, :m], roi[:, -m:] = 0, 0, 0, 0
    roi, _ = denoise(roi)
    dash, solid, _, _ = split_dash_solid(roi)
    solid = drop_rulers(solid, int(0.4 * W))
    solid = template_strokes(solid, LINK_PX, MIN_TEMPLATE_PX)
    gc, gw = ground_candidates(dash, solid, HIDDEN_GROUND_WEIGHT)
    ground_px = best_path(gc, win=TRACE_WINDOW, weights=gw)
    grid_rows = [((a + b) / 2 - y0) * sy for a, b in frame.hlines]

    def trace(mask):
        d = snap_top(mask, best_path(candidates(mask)))
        return fill_along_gridlines(d, grid_rows, int(1.0 * CANON_PPF))

    return _finish_with_retry(ground_px, trace, solid, roi, W, H, cfg, "raster", refine=True)


def _erase_chain(mask: np.ndarray, chain: dict, half: int = 4) -> np.ndarray:
    """`mask` without the strokes a traced chain ran along."""
    band = np.zeros_like(mask)
    for x, y in chain.items():
        band[max(0, int(y) - half):int(y) + half + 1, max(0, x - 1):x + 2] = 1
    band = cv2.dilate(band, np.ones((3, 3), np.uint8))
    return mask & (1 - band)


def _finish_with_retry(ground_px, trace, solid, roi, W, H, cfg, source, refine) -> Surfaces:
    """Trace the design and finish. When the strongest solid line turns out
    to be a buried pipe or utility (rejected whole, leaving no design over
    the ground), erase it and trace again: the template is usually the next
    line down the list. The rejected run is still reported."""
    design_px = trace(solid)
    s = _finish(ground_px, design_px, solid, roi, W, H, cfg, source, refine)
    if s.overlap.any() or not s.trimmed or not design_px:
        return s
    rest = _erase_chain(solid, design_px)
    if not rest.any():
        return s
    again = _finish(ground_px, trace(rest), rest, roi, W, H, cfg, source, refine)
    if not again.overlap.any():
        return s
    again.trimmed = s.trimmed + again.trimmed
    return again


def _partial_grid_lines(ink: np.ndarray, bands: list[tuple[int, int]], pitch: float,
                        axis: int) -> list[tuple[int, int]]:
    """Grid lines drawn across only part of the plot (some sheets do this
    near the axes) are missed by frame detection, which looks for full-length
    lines, yet they would survive as long, perfectly straight "solid" strokes.
    The lattice is regular, so look on every expected grid position that has
    no detected line for a straight run at least two squares long.
    axis=0: horizontal lines (rows), axis=1: vertical lines (columns)."""
    if len(bands) < 2:
        return []
    centres = sorted((a + b) / 2 for a, b in bands)
    n = ink.shape[axis]
    expected, k0 = [], centres[0]
    k = int(np.floor(-k0 / pitch))
    while k0 + k * pitch < n:
        c = k0 + k * pitch
        if 0 <= c < n and min(abs(c - x) for x in centres) > 0.25 * pitch:
            expected.append(c)
        k += 1
    run = int(2 * pitch)
    shape = (run, 1) if axis == 0 else (1, run)       # cv2 kernel: (width, height)
    opened = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, shape))
    prof = opened.sum(1 - axis)                         # ink along each row (axis 0) / column
    out = []
    for c in expected:
        lo, hi = max(0, int(c) - 4), min(n, int(c) + 5)
        hit = np.where(prof[lo:hi] >= run)[0]
        if len(hit):
            out.append((lo + int(hit.min()), lo + int(hit.max())))
    return out


# ------------------------------------------------------------------ vector

def _path_segments(d: dict) -> list[tuple]:
    segs = []
    for it in d["items"]:
        op = it[0]
        if op == "l":
            segs.append((it[1], it[2]))
        elif op == "c":
            pts = [it[1], it[2], it[3], it[4]]
            # flatten the Bezier into 8 chords
            prev = pts[0]
            for t in np.linspace(0, 1, 9)[1:]:
                a = (1 - t) ** 3
                b = 3 * (1 - t) ** 2 * t
                c = 3 * (1 - t) * t ** 2
                e = t ** 3
                p = (a * pts[0].x + b * pts[1].x + c * pts[2].x + e * pts[3].x,
                     a * pts[0].y + b * pts[1].y + c * pts[2].y + e * pts[3].y)
                segs.append((prev, p))
                prev = type(pts[0])(*p)
        elif op == "re":
            r = it[1]
            q = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
            segs += [(q[i], q[(i + 1) % 4]) for i in range(4)]
        elif op == "qu":
            q = it[1]
            pts = [q.ul, q.ur, q.lr, q.ll]
            segs += [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    return [(_xy(a), _xy(b)) for a, b in segs]


def _xy(p) -> tuple[float, float]:
    return (p.x, p.y) if hasattr(p, "x") else (float(p[0]), float(p[1]))


def _is_dashed(d: dict) -> bool:
    dash = (d.get("dashes") or "").strip()
    return bool(dash) and not dash.startswith("[]")


def vector_strokes(frame: Frame, img: PageImage, cfg: PipelineConfig):
    """Dashed and solid data strokes inside the frame, in canonical frame-local
    pixels. Grid lines, tick marks and text glyphs are filtered out; filled
    pavement bands count as solid strokes (their outline)."""
    k = img.scale
    sx, sy, W, H = _canon_size(frame, cfg)
    fw, fh = frame.right - frame.left, frame.bottom - frame.top
    edge = 0.08 * frame.pitch_y
    dashed, solid = [], []
    for d in img.page.get_drawings():
        kind = d.get("type") or ""
        if "s" not in kind and not _is_pavement_fill(d, k, frame):
            continue
        r = d["rect"]
        # page points -> (possibly rotated) page-image pixels
        (rx0, ry0), (rx1, ry1) = img.to_view(r.x0 * k, r.y0 * k), img.to_view(r.x1 * k, r.y1 * k)
        rx0, rx1 = sorted((rx0, rx1))
        ry0, ry1 = sorted((ry0, ry1))
        if rx1 < frame.left or rx0 > frame.right or ry1 < frame.y0 or ry0 > frame.y1:
            continue
        if max(rx1 - rx0, ry1 - ry0) < 0.25 * frame.pitch_x:   # text glyphs, ticks, specks
            continue
        is_dash = _is_dashed(d)
        for (ax, ay), (bx, by) in _path_segments(d):
            ax, ay = img.to_view(ax * k, ay * k)
            bx, by = img.to_view(bx * k, by * k)
            # near-flat, not exactly flat: CAD exports often store grid lines
            # with a pixel of drift over their full length
            horiz = abs(ay - by) < max(0.2, 0.002 * abs(ax - bx))
            vert = abs(ax - bx) < max(0.2, 0.002 * abs(ay - by))
            # grid & frame lines span most of the frame; the frame's own top
            # and bottom (offset axis) lines are often drawn in short pieces
            # (grid lines are always solid -- a long flat stretch of dashed
            # existing ground must never be mistaken for one)
            if horiz and not is_dash and (abs(ax - bx) > 0.5 * fw
                                          or min(abs(ay - frame.top), abs(ay - frame.bottom)) < 3):
                continue
            if vert and abs(ay - by) > 0.5 * fh and not is_dash:
                continue
            # axis tick marks: short solid strokes hugging the frame edge
            # (often drawn as one path spanning the whole axis)
            if not is_dash and max(_edge_dist(frame, ax, ay), _edge_dist(frame, bx, by)) < edge:
                continue
            seg = ((ax - frame.left) * sx, (ay - frame.y0) * sy,
                   (bx - frame.left) * sx, (by - frame.y0) * sy)
            (dashed if is_dash else solid).append(seg)
    return dashed, solid, W, H


def _is_pavement_fill(d: dict, k: float, frame: Frame) -> bool:
    """Some CAD exports draw the pavement as a filled dark band with no
    outline stroke. Its outline is the finished grade on top and the
    subgrade below, so it is read as solid linework: a dark fill that is
    thin (under 3 ft) and at least half a grid square long."""
    fill = d.get("fill")
    if "f" not in (d.get("type") or "") or not fill or max(fill) > 0.35:
        return False
    r = d["rect"]
    return r.height * k < 0.3 * frame.pitch_y and r.width * k >= 0.5 * frame.pitch_x


def _edge_dist(frame: Frame, x: float, y: float) -> float:
    return min(abs(y - frame.top), abs(y - frame.bottom), abs(x - frame.left), abs(x - frame.right))


def _draw(segs, W, H) -> np.ndarray:
    m = np.zeros((H, W), np.uint8)
    for x0, y0, x1, y1 in segs:
        cv2.line(m, (int(round(x0)), int(round(y0))), (int(round(x1)), int(round(y1))), 1, 2)
    m[:2], m[-2:], m[:, :2], m[:, -2:] = 0, 0, 0, 0
    return m


def vector_surfaces(frame: Frame, img: PageImage, cfg: PipelineConfig) -> Surfaces | None:
    if img.page is None:
        return None
    dashed, solid, W, H = vector_strokes(frame, img, cfg)
    if len(dashed) < 3 or len(solid) < 2:
        return None          # this sheet doesn't draw ground dashed -- fall back to raster
    dmask, smask = _draw(dashed, W, H), _draw(solid, W, H)
    smask = template_strokes(smask, LINK_PX, MIN_TEMPLATE_PX)
    gc, gw = ground_candidates(dmask, smask, HIDDEN_GROUND_WEIGHT)
    ground_px = best_path(gc, win=TRACE_WINDOW, weights=gw)
    return _finish_with_retry(ground_px, lambda m: snap_top(m, best_path(candidates(m))),
                              smask, dmask | smask, W, H, cfg, "vector", refine=False)
