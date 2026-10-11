"""
Whole-plan-set orchestration: PDF in, roads + volumes out.

    for every page (in parallel):
        load page            pages.load_page        raster scan or vector render
        find frames          frames.find_frames     one per cross-section
        read stations        frames.label_frames    text layer, else OCR
        trace surfaces       surfaces.*_surfaces    vector strokes, else pixels
        measure              surfaces.measure       fill / cut ft^2
        render overlay       render.overlay         audit image
    repair stations          stations.repair        across the whole document
    group into roads         roads.group_into_roads
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

from .config import PipelineConfig, get_config
from .frames import find_frames, label_frames
from .pages import could_hold_sections, load_page, sideways_labels
from .render import encode_png, overlay
from .roads import Road, StationEntry, group_into_roads
from .stations import StationRead, repair
from .surfaces import Surfaces, _canon_size, measure, raster_surfaces, vector_surfaces
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
    geometry: dict | None = None       # page-space outline + traced lines, for the annotated PDF

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
        "ground": line(surf.ground),
        "finished": line(surf.design),
        "subgrade": line(surf.surface("subgrade")),
    }


def _measure_page(pdf_path: str, index: int, cfg: PipelineConfig, overlays: bool) -> list[SectionResult]:
    doc = fitz.open(pdf_path)
    try:
        if not could_hold_sections(doc, index):
            return []
        img = load_page(doc, index, cfg.vector_dpi)
        frames = label_frames(find_frames(img, cfg.ink_thresh), img, cfg.ink_thresh)
        rotated_plot = img.kind == "raster" or sideways_labels(img.page)
        if rotated_plot and not any(f.station_label for f in frames):
            # nothing readable upright: the sections may be plotted sideways
            for k in (-1, 1):
                turned = img.rotated(k)
                alt = label_frames(find_frames(turned, cfg.ink_thresh), turned, cfg.ink_thresh)
                if sum(f.station_label is not None for f in alt) > sum(f.station_label is not None for f in frames):
                    frames, img = alt, turned
        out = []
        for i, f in enumerate(frames):
            warnings: list[str] = []
            use_vector = img.kind == "vector" and not cfg.force_raster
            surf = vector_surfaces(f, img, cfg) if use_vector else None
            method = "vector"
            if surf is None:
                surf, method = raster_surfaces(f, img, cfg), "raster"
            area = measure(surf, cfg.design_surface)
            alt = measure(surf, "finished" if cfg.design_surface == "subgrade" else "subgrade")
            if not surf.overlap.any():
                warnings.append("no proposed design found over existing ground -- area is zero")
            if max(surf.max_gap_ground_ft, surf.max_gap_design_ft) > cfg.gap_warn_ft:
                warnings.append(
                    f"a surface was bridged across a {max(surf.max_gap_ground_ft, surf.max_gap_design_ft):.0f} ft "
                    f"gap with no ink -- area over that span is a straight-line estimate")
            for t in surf.trimmed:
                warnings.append(
                    f"ignored a {t['run_ft']:.0f} ft run {t['depth_ft']:.1f} ft below ground on the "
                    f"{t['side']} -- looks like a buried pipe, not graded surface")
            for st in surf.structures:
                warnings.append(
                    f"design line from {st['x_from']:+.0f} to {st['x_to']:+.0f} ft hangs above the ground "
                    f"at both ends (bridge deck or structure) -- not counted as fill")
            png = encode_png(overlay(surf, f, img, cfg, surface=cfg.design_surface)) if overlays else None
            out.append(SectionResult(
                page=img.number, index=i, station_label=f.station_label, station_ft=f.station_ft,
                label_source=f.label_source, label_confidence=f.label_confidence,
                label_candidates=tuple(f.label_candidates),
                fill_ft2=round(area.fill_ft2, 2), cut_ft2=round(area.cut_ft2, 2), method=method,
                alt_fill_ft2=round(alt.fill_ft2, 2), alt_cut_ft2=round(alt.cut_ft2, 2),
                bbox=(f.top, f.bottom, f.left, f.right), page_kind=img.kind,
                px_per_ft=(f.pitch_x / cfg.grid_ft, f.pitch_y / cfg.grid_ft), rotation=img.rot,
                warnings=warnings, overlay_png=png, geometry=_geometry(surf, f, img, cfg),
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
    overlays: bool = True,
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
    reads = repair([StationRead(s.station_label, s.station_ft, s.label_confidence, s.label_source,
                                candidates=s.label_candidates) for s in sections])
    warnings = []
    for s, r in zip(sections, reads):
        if r.source == "inferred":
            s.station_label, s.station_ft, s.label_source = r.label, r.station_ft, "inferred"
            s.warnings.append(r.note)
        elif r.label != s.station_label:      # an alternative OCR reading was chosen
            s.station_label, s.station_ft, s.label_confidence = r.label, r.station_ft, r.confidence
    unlabelled = [s for s in sections if s.station_ft is None]
    if unlabelled:
        warnings.append(
            f"{len(unlabelled)} cross-section(s) had no readable station and could not be placed "
            f"along a road: " + ", ".join(f"page {s.page}" for s in unlabelled[:10]))

    entries = [StationEntry(s.station_label, s.station_ft, s.page, s)
               for s in sections if s.station_ft is not None]
    roads = group_into_roads(entries)
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


class _AltArea:
    """A section seen through its alternative-surface areas, for volume.py."""

    def __init__(self, s: SectionResult):
        self.station_label, self.station_ft = s.station_label, s.station_ft
        self.fill_ft2, self.cut_ft2 = s.alt_fill_ft2, s.alt_cut_ft2
