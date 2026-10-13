"""Stage 5 -- measure: areas of a traced section, and what to warn about."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import PipelineConfig
from ..surfaces import Area, Surfaces, area_strips, measure

# Why a section measures (almost) no cut or fill -- usually the drawing,
# not a failure: shown to the user instead of a bare 0 / 0.
ZERO_REASONS = {
    "structure": "Bridge or structure: the proposed line spans over the ground, so there is no earthwork here.",
    "no_design": "No proposed surface is drawn on this section (existing ground only: outside the "
                 "construction limits, a match line, or a section that only shows utilities).",
    "matches_existing": "The proposed surface follows existing ground (resurfacing / match existing), "
                        "so there is no cut or fill.",
}
ZERO_FT2 = 0.5


@dataclass
class SectionMeasure:
    area: Area                      # to cfg.design_surface
    alt: Area                       # to the other proposed surface
    strips: dict                    # surface -> (fill, cut) ft² per 1 ft strip from the frame's left edge
    warnings: list[str] = field(default_factory=list)
    zero_reason: str | None = None


def zero_reason(surf: Surfaces, area: Area) -> str | None:
    """Why a section measures no earthwork, when it doesn't (see ZERO_REASONS)."""
    if area.fill_ft2 + area.cut_ft2 >= ZERO_FT2:
        return None
    if not surf.overlap.any():
        return "structure" if surf.structures else "no_design"
    return "matches_existing"


def measure_section(surf: Surfaces, cfg: PipelineConfig) -> SectionMeasure:
    """Fill and cut to both proposed surfaces, the 1 ft strips the left /
    right split is made from, and the warnings a reviewer should see."""
    area = measure(surf, cfg.design_surface)
    alt = measure(surf, "finished" if cfg.design_surface == "subgrade" else "subgrade")
    warnings: list[str] = []
    gap = max(surf.max_gap_ground_ft, surf.max_gap_design_ft)
    if gap > cfg.gap_warn_ft:
        warnings.append(f"a surface was bridged across a {gap:.0f} ft gap with no ink -- area over that span is a "
                        f"straight-line estimate")
    for t in surf.trimmed:
        warnings.append(f"ignored a {t['run_ft']:.0f} ft run {t['depth_ft']:.1f} ft below ground on the "
                        f"{t['side']} -- looks like a buried pipe, not graded surface")
    for st in surf.structures:
        warnings.append(f"design line from {st['x_from']:+.0f} to {st['x_to']:+.0f} ft hangs above the ground "
                        f"at both ends (bridge deck or structure) -- not counted as fill")
    strips = {sf: tuple([round(float(v), 3) for v in a] for a in area_strips(surf, sf)) for sf in ("subgrade", "finished")}
    return SectionMeasure(area=area, alt=alt, strips=strips, warnings=warnings, zero_reason=zero_reason(surf, area))
