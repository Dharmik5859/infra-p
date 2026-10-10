"""
Tunables for the earthwork pipeline, in one frozen dataclass.

Pixel constants used while tracing live in tracing.py and are expressed at
the canonical resolution (surfaces.CANON_PPF), so nothing here depends on
the scan's DPI or the sheet's drawing scale.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    # --- sheet geometry ---
    grid_ft: float = 10.0          # real-world size of one MAJOR grid square
    ink_thresh: int = 200          # gray level below which a pixel is ink; the light
                                   # 1-2 ft minor grid of 23-series sheets prints ~219
    vector_dpi: int = 300          # render resolution for vector (CAD-export) pages
    force_raster: bool = False     # trace vector pages from pixels too (evaluation only)

    # --- curve cleanup ---
    despike_win: int = 9
    despike_px: float = 4.0

    # --- buried-service (false cut) filtering ---
    buried_run_ft: float = 25.0
    buried_depth_ft: float = 3.5

    # --- gap handling ---
    gap_refine_ft: float = 3.0
    gap_tol_px: float = 7.0
    gap_warn_ft: float = 12.0

    # --- what "proposed surface" means for earthwork ---
    design_surface: str = "subgrade"   # "subgrade": bottom of the pavement structure
                                       # (standard earthwork practice, and what the
                                       # estimators' takeoffs measure); "finished":
                                       # top of pavement / finished grade

    # --- overlay colours (BGR) ---
    fill_color_bgr: tuple[int, int, int] = (79, 158, 46)      # green
    cut_color_bgr: tuple[int, int, int] = (59, 59, 209)       # red
    ground_line_bgr: tuple[int, int, int] = (176, 112, 40)    # existing ground
    design_line_bgr: tuple[int, int, int] = (30, 30, 30)      # proposed finished grade
    subgrade_line_bgr: tuple[int, int, int] = (0, 140, 230)   # proposed subgrade
    overlay_alpha: float = 0.55


# One configuration handles every sheet format seen so far: 19-series strip
# scans, 23-series sheet scans and vector CAD exports. Format differences
# (resolution, drawing scale, single vs stacked sections) are detected per
# page, not configured. Presets remain the place for a future series that
# genuinely needs different settings.
PRESETS: dict[str, PipelineConfig] = {
    "auto": PipelineConfig(),
}


def get_config(name: str = "auto") -> PipelineConfig:
    try:
        return PRESETS[name]
    except KeyError as e:
        raise KeyError(f"Unknown preset {name!r}. Known presets: {list(PRESETS)}") from e
