"""
Whole-plan-set orchestration: PDF in, roads + volumes out.

    for every page (in parallel):
        ingest               stages.ingest          raster scan or vector render
        detect               stages.detect          frames + station labels
        calibrate            stages.calibrate       ft per grid square, each axis; centreline
        trace                stages.trace           vector strokes, else pixels
        measure              stages.measure         fill / cut ft^2, strips, warnings
        render overlay       render.overlay         audit image
    decode stations          stages.decode_stations across the whole document
    group into roads         roads.group_into_roads
    confidence               confidence.score_sections  0-100 per section, alerts below 85
    volumes                  volume.average_end_area_volume

Pages with no labelled cross-section frame (cover, notes, plan and profile
sheets) simply contribute nothing; that is the page classification.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pymupdf as fitz

from .confidence import score_sections
from .config import PipelineConfig, get_config
from .render import encode_png, overlay, overlay_scale, profile
from .roads import Road, StationEntry, group_into_roads
from .sides import measured_sides
from .stages import calibrate, decode_stations, detect, ingest, measure_section, trace
from .stages.calibrate import centre_ft
from .stages.measure import ZERO_FT2, ZERO_REASONS, zero_reason as _zero_reason  # noqa: F401 (re-exported)
from .surfaces import CANON_PPF, Surfaces, _canon_size
from .volume import RoadVolumeResult, average_end_area_volume


@dataclass
class SectionResult:
    page: int
    index: int                         # position on the page, top to bottom
    station_label: str | None
    station_ft: float | None
    label_source: str | None
    label_confidence: float
    label_candidates: tuple[str, ...]
    fill_ft2: float
    cut_ft2: float
    method: str                        # "vector" | "raster"
    alt_fill_ft2: float                # the same section measured to the other surface
    alt_cut_ft2: float                 # (finished grade when the default is subgrade)
    bbox: tuple[int, int, int, int]    # top, bottom, left, right (page pixels)
    page_kind: str
    px_per_ft: tuple[float, float]     # page pixels per ft, horizontal / vertical
    rotation: int                      # quarter turns the page was read at (np.rot90 k)
    warnings: list[str] = field(default_factory=list)
    overlay_png: bytes | None = None
    overlay_px_per_ft: float | None = None  # overlay image pixels per ft (both axes)
    profile: dict | None = None        # traced lines in overlay pixels (render.profile)
    geometry: dict | None = None       # page-space outline + traced lines, for the annotated PDF
    zero_reason: str | None = None     # why a section has no earthwork (see ZERO_REASONS)
    centre_ft: float | None = None     # centreline (offset 0), ft from the frame's left edge
    centre_source: str | None = None   # "text" / "scan" (read off the offset axis), "neighbour", "assumed"
    strips: dict | None = None         # surface -> (fill, cut) ft² per 1 ft strip from the left edge
    sides: dict | None = None          # surface -> {"left"|"right": {"fill_ft2", "cut_ft2"}}, as traced
    scale: dict | None = None          # stages.FrameScale.as_dict(): ft per grid square each axis, and source
    confidence: dict | None = None     # confidence.score(): {"score", "passed", "deductions", "alerts"}

    @property
    def net_ft2(self) -> float:
        return self.fill_ft2 - self.cut_ft2


@dataclass
class PlanSetResult:
    pages: int
    cross_section_pages: int
    sections: list[SectionResult]      # document order, each road ascending
    roads: list[Road]
    volumes: list[RoadVolumeResult]    # parallel to roads, measured to cfg.design_surface
    alt_volumes: list[RoadVolumeResult]  # parallel to roads, measured to the other surface
    warnings: list[str]
    timing: dict
    design_surface: str = "subgrade"


GEOMETRY_STEP = 4      # canonical columns between stored points (~0.3 ft)


def _geometry(surf: Surfaces, f, img, cfg: PipelineConfig) -> dict | None:
    """The section in PDF page coordinates: its frame corners, and the
    ground and both proposed surfaces as polylines (None where untraced),
    so an annotated copy of the original PDF can be drawn later."""
    if img.placement is None:
        return None
    sx, sy, _, _ = _canon_size(f, cfg)
    cols = np.arange(0, surf.width, GEOMETRY_STEP)
    vx = f.left + (cols + 0.5) / sx

    def line(rows):
        out = []
        for x, r in zip(vx, rows[cols]):
            out.append(None if np.isnan(r) else img.page_point(x, f.y0 + r / sy))
        return out

    corner = lambda x, y: img.page_point(x, y)
    return {
        # top-left, top-right, bottom-left of the frame, as drawn on the sheet
        "frame": [corner(f.left, f.top), corner(f.right, f.top), corner(f.left, f.bottom)],
        # the same corners of the section image (overlay), so areas the user
        # marks on it can be drawn on the page: image (u, v) in 0..1 maps to
        # canvas[0] + u (canvas[1] - canvas[0]) + v (canvas[2] - canvas[0])
        "canvas": [corner(f.left, f.y0), corner(f.left + surf.width / sx, f.y0),
                   corner(f.left, f.y0 + surf.height / sy)],
        "image_size": [round(surf.width * overlay_scale(surf)), round(surf.height * overlay_scale(surf))],
        "ground": line(surf.ground),
        "finished": line(surf.design),
        "subgrade": line(surf.surface("subgrade")),
    }


def _measure_page(pdf_path: str, index: int, cfg: PipelineConfig, overlays: bool | str) -> list[SectionResult]:
    doc = fitz.open(pdf_path)
    try:
        img = ingest(doc, index, cfg)
        if img is None:
            return []
        frames, img = detect(img, cfg)
        page_cache: dict = {}
        out = []
        for i, f in enumerate(frames):
            scale = calibrate(f, img, cfg, page_cache)
            surf, method = trace(f, img, cfg)
            m = measure_section(surf, cfg)
            png = encode_png(overlay(surf, f, img, cfg, surface=cfg.design_surface,
                                     shade=overlays != "lines")) if overlays else None
            out.append(SectionResult(
                page=img.number, index=i, station_label=f.station_label, station_ft=f.station_ft,
                label_source=f.label_source, label_confidence=f.label_confidence,
                label_candidates=tuple(f.label_candidates),
                fill_ft2=round(m.area.fill_ft2, 2), cut_ft2=round(m.area.cut_ft2, 2), method=method,
                alt_fill_ft2=round(m.alt.fill_ft2, 2), alt_cut_ft2=round(m.alt.cut_ft2, 2),
                bbox=(f.top, f.bottom, f.left, f.right), page_kind=img.kind,
                px_per_ft=(scale.px_per_ft_x, scale.px_per_ft_y), rotation=img.rot,
                warnings=m.warnings, overlay_png=png,
                overlay_px_per_ft=round(CANON_PPF * overlay_scale(surf), 4) if png else None,
                profile=profile(surf) if png else None, geometry=_geometry(surf, f, img, cfg),
                zero_reason=m.zero_reason, centre_ft=centre_ft(f, scale), centre_source=scale.centre_source,
                strips=m.strips, scale=scale.as_dict(),
            ))
        return out
    finally:
        doc.close()


def _document_order(by_page: dict[int, list[SectionResult]]) -> list[SectionResult]:
    """Sheets usually stack stations DESCENDING top to bottom. Detect that from
    the pages whose labels are readable, then flip every page so the document
    reads in ascending station order -- what road grouping expects."""
    down = up = 0
    for secs in by_page.values():
        ft = [s.station_ft for s in secs if s.station_ft is not None]
        for a, b in zip(ft, ft[1:]):
            down += b < a
            up += b > a
    out = []
    for p in sorted(by_page):
        secs = by_page[p]
        out.extend(reversed(secs) if down > up else secs)
    return out


def process_plan_set(
    pdf_path: str,
    cfg: PipelineConfig | str | None = None,
    workers: int | None = None,
    overlays: bool | str = True,       # True: shaded audit images; "lines": traced lines only
    progress: Callable[[int, int], None] | None = None,
    pages: list[int] | None = None,
) -> PlanSetResult:
    """`pages`: 1-based page numbers to process (default: every page)."""
    if cfg is None or isinstance(cfg, str):
        cfg = get_config(cfg or "auto")
    t0 = time.time()
    with fitz.open(pdf_path) as doc:
        n_pages = len(doc)
    todo = [p - 1 for p in (pages or range(1, n_pages + 1)) if 1 <= p <= n_pages]
    workers = workers or min(4, os.cpu_count() or 1)

    by_page: dict[int, list[SectionResult]] = {}
    done = 0
    if workers > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_measure_page, pdf_path, i, cfg, overlays): i for i in todo}
            for fut in as_completed(futs):
                by_page[futs[fut] + 1] = fut.result()
                done += 1
                if progress:
                    progress(done, len(todo))
    else:
        for i in todo:
            by_page[i + 1] = _measure_page(pdf_path, i, cfg, overlays)
            done += 1
            if progress:
                progress(done, len(todo))
    t_pages = time.time() - t0

    sections = _document_order(by_page)
    warnings = decode_stations(sections)

    _place_centrelines(sections)

    entries = [StationEntry(s.station_label, s.station_ft, s.page, s)
               for s in sections if s.station_ft is not None]
    roads = group_into_roads(entries)
    score_sections(sections, roads)
    volumes = [average_end_area_volume([e.ref for e in r.entries], road_label=r.label) for r in roads]
    alt_volumes = [average_end_area_volume([_AltArea(e.ref) for e in r.entries], road_label=r.label)
                   for r in roads]

    timing = {
        "total_seconds": round(time.time() - t0, 1),
        "page_seconds": round(t_pages, 1),
        "sections": len(sections),
        "workers": workers,
    }
    return PlanSetResult(
        pages=len(todo),
        cross_section_pages=sum(1 for v in by_page.values() if v),
        sections=sections, roads=roads, volumes=volumes, alt_volumes=alt_volumes,
        warnings=warnings, timing=timing, design_surface=cfg.design_surface,
    )


def _place_centrelines(sections: list[SectionResult]) -> None:
    """Every section gets a centreline and its left / right areas. Where the
    offset axis could not be read, the nearest section in document order with
    a read centreline and the same frame width lends its own (sheets of one
    series share the axis layout); failing that, the middle of the grid."""
    width = lambda s: s.bbox[3] - s.bbox[2]
    read = [i for i, s in enumerate(sections) if s.centre_ft is not None]
    for i, s in enumerate(sections):
        if s.centre_ft is None:
            near = sorted((j for j in read if abs(width(sections[j]) - width(s)) <= 0.02 * width(s)),
                          key=lambda j: abs(j - i))
            if near:
                s.centre_ft, s.centre_source = sections[near[0]].centre_ft, "neighbour"
                s.warnings.append("the offset axis could not be read here -- the centreline (left / right "
                                  "split) is taken from the neighbouring section")
            else:
                s.centre_ft = round((width(s)) / (s.px_per_ft[0]) / 2, 2)
                s.centre_source = "assumed"
                s.warnings.append("the offset axis could not be read -- the centreline (left / right split) "
                                  "is assumed at the middle of the grid")
        if s.strips:
            s.sides = {sf: measured_sides(fill, cut, s.centre_ft) for sf, (fill, cut) in s.strips.items()}


class _AltArea:
    """A section seen through its alternative-surface areas, for volume.py."""

    def __init__(self, s: SectionResult):
        self.station_label, self.station_ft = s.station_label, s.station_ft
        self.fill_ft2, self.cut_ft2 = s.alt_fill_ft2, s.alt_cut_ft2
