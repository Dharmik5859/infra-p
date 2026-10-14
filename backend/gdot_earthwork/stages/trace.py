"""Stage 4 -- trace: existing ground and the proposed surfaces of a section."""
from __future__ import annotations

from ..config import PipelineConfig
from ..frames import Frame
from ..pages import PageImage
from ..surfaces import Surfaces, raster_surfaces, vector_surfaces


def trace(frame: Frame, img: PageImage, cfg: PipelineConfig, exclude=None, erase=None,
          stage_pen: bool = False) -> tuple[Surfaces, str]:
    """The section's traced lines, resampled to the canonical resolution
    using the frame's calibrated feet per grid square. Vector pages are read
    from their strokes; scans (or vector pages where the strokes cannot be
    used) from their pixels. `exclude`: page-pixel x ranges whose proposed
    lines belong to another construction stage (staging.py), traced without;
    `erase`: annotation lines (x_from, x_to, y) that are not surfaces;
    `stage_pen`: a staged plan set, whose other stages are drawn in grey.
    Returns (surfaces, "vector" | "raster")."""
    if img.kind == "vector" and not cfg.force_raster:
        surf = vector_surfaces(frame, img, cfg, exclude, erase)
        if surf is not None:
            return surf, "vector"
    return raster_surfaces(frame, img, cfg, exclude, erase, stage_pen), "raster"
