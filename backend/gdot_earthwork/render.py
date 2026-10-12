"""
Audit overlay for one cross-section: the source drawing, the traced
surfaces, and the fill/cut regions between them -- so a reviewer can see
at a glance whether the numbers were measured off the right lines.
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import PipelineConfig
from .frames import Frame
from .pages import PageImage
from .surfaces import Surfaces


def overlay_scale(s: Surfaces, max_width: int = 1800) -> float:
    """How much `overlay` shrinks the canonical frame (1 = not at all)."""
    return min(1.0, max_width / s.width) if s.width else 1.0


def overlay(s: Surfaces, frame: Frame, img: PageImage, cfg: PipelineConfig,
            max_width: int = 1800, surface: str = "subgrade") -> np.ndarray:
    gray = img.gray[frame.y0:frame.y1 + 1, frame.left:frame.right + 1]
    base = cv2.resize(gray, (s.width, s.height), interpolation=cv2.INTER_AREA)
    # fade the sheet so the measurement reads on top of it
    base = (255 - (255 - base.astype(np.float32)) * 0.45).astype(np.uint8)
    out = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)

    rows = np.arange(s.height)[:, None]
    top = s.surface(surface)
    ov = ~np.isnan(s.ground) & ~np.isnan(top)
    g = np.where(ov, s.ground, np.nan)
    d = np.where(ov, top, np.nan)
    with np.errstate(invalid="ignore"):
        fill = (rows >= d) & (rows < g)
        cut = (rows >= g) & (rows < d)
    layer = out.copy()
    layer[fill] = cfg.fill_color_bgr
    layer[cut] = cfg.cut_color_bgr
    a = cfg.overlay_alpha
    mask = (fill | cut)[..., None]
    out = np.where(mask, (out * (1 - a) + layer * a).astype(np.uint8), out)

    def poly(y, colour):
        cols = np.where(~np.isnan(y))[0]
        if len(cols) < 2:
            return
        # break the polyline where the trace has a hole
        breaks = np.where(np.diff(cols) > 1)[0] + 1
        for seg in np.split(cols, breaks):
            if len(seg) > 1:
                pts = np.stack([seg, y[seg]], 1).round().astype(np.int32)
                cv2.polylines(out, [pts], False, colour, 2, cv2.LINE_AA)

    poly(s.ground, cfg.ground_line_bgr)
    poly(s.design, cfg.design_line_bgr)
    if surface == "subgrade" and s.subgrade is not None:
        # subgrade only where it departs from finished grade (under pavement)
        sub = np.where(np.abs(s.subgrade - s.design) > 2, s.subgrade, np.nan)
        poly(sub, cfg.subgrade_line_bgr)
    f = overlay_scale(s, max_width)
    if f < 1:
        out = cv2.resize(out, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return out


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()
