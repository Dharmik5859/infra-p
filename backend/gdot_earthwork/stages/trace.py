"""Stage 4 -- trace: existing ground and the proposed surfaces of a section."""
from __future__ import annotations

from ..config import PipelineConfig
from ..frames import Frame
from ..pages import PageImage
from ..surfaces import Surfaces, raster_surfaces, vector_surfaces


def trace(frame: Frame, img: PageImage, cfg: PipelineConfig) -> tuple[Surfaces, str]:
    """The section's traced lines, resampled to the canonical resolution
    using the frame's calibrated feet per grid square. Vector pages are read
    from their strokes; scans (or vector pages where the strokes cannot be
    used) from their pixels. Returns (surfaces, "vector" | "raster")."""
    if img.kind == "vector" and not cfg.force_raster:
        surf = vector_surfaces(frame, img, cfg)
        if surf is not None:
            return surf, "vector"
    return raster_surfaces(frame, img, cfg), "raster"
