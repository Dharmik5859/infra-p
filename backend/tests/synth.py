"""
Synthetic cross-section sheets with exactly known answers.

Draws GDOT-style sections -- 10 ft grid, offset axis with ticks and
labels, station label, dashed existing ground, solid proposed template --
into a vector PDF, and optionally a "scanned" copy (the same page rasterized
and embedded as a single image, with no text layer). Because the geometry
is generated, the true fill/cut area of every section is known exactly.
"""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf as fitz
import numpy as np

PT_PER_FT = 3.6          # drawing scale: 1 in = 20 ft  ->  72 pt / 20 ft
GRID_FT = 10.0


@dataclass
class SectionSpec:
    station: str                         # e.g. "12+50"
    ground: list[tuple[float, float]]    # (offset ft, elevation ft) polyline
    design: list[tuple[float, float]]


def _interp(poly, x):
    xs, ys = zip(*poly)
    return np.interp(x, xs, ys, left=np.nan, right=np.nan)


def true_areas(spec: SectionSpec) -> tuple[float, float]:
    """Exact fill and cut (ft^2) between the two polylines."""
    x0 = max(spec.ground[0][0], spec.design[0][0])
    x1 = min(spec.ground[-1][0], spec.design[-1][0])
    x = np.linspace(x0, x1, 200001)
    d = _interp(spec.design, x) - _interp(spec.ground, x)     # +ve: design above ground = fill
    dx = x[1] - x[0]
    return float(np.clip(d, 0, None).sum() * dx), float(np.clip(-d, 0, None).sum() * dx)


def true_side_areas(spec: SectionSpec) -> dict:
    """Exact fill and cut (ft^2) left (offset < 0) and right of the centreline."""
    x0 = max(spec.ground[0][0], spec.design[0][0])
    x1 = min(spec.ground[-1][0], spec.design[-1][0])
    x = np.linspace(x0, x1, 200001)
    d = _interp(spec.design, x) - _interp(spec.ground, x)
    dx = x[1] - x[0]
    out = {}
    for side, keep in (("left", x < 0), ("right", x >= 0)):
        out[side] = {"fill_ft2": float(np.clip(d[keep], 0, None).sum() * dx),
                     "cut_ft2": float(np.clip(-d[keep], 0, None).sum() * dx)}
    return out


def embankment(station: str, ground_elev: float, height: float, top_half: float = 18.0,
               slope: float = 2.0, tilt: float = 0.0) -> SectionSpec:
    """A road on fill: flat-ish ground, template with 2:1 side slopes."""
    g = [(-140, ground_elev - 140 * tilt), (-40, ground_elev - 40 * tilt + 0.4), (25, ground_elev + 25 * tilt - 0.3),
         (140, ground_elev + 140 * tilt)]
    top = ground_elev + height
    run = height * slope
    d = [(-top_half - run, ground_elev - (top_half + run) * tilt), (-top_half, top), (0, top + 0.36),
         (top_half, top), (top_half + run, ground_elev + (top_half + run) * tilt)]
    return SectionSpec(station, g, d)


def cut_section(station: str, ground_elev: float, depth: float) -> SectionSpec:
    """A road in cut with ditches: ground above the template."""
    g = [(-140, ground_elev), (-60, ground_elev + 1.0), (60, ground_elev + 1.5), (140, ground_elev + 1.0)]
    base = ground_elev - depth
    d = [(-24 - depth * 2, ground_elev + 1.0 - 0.0), (-24, base - 1.5), (-20, base - 1.5), (-16, base),
         (16, base), (20, base - 1.5), (24, base - 1.5), (24 + depth * 2 + 3, ground_elev + 1.4)]
    return SectionSpec(station, g, d)


def rolling_section(station: str, elev: float, amp: float = 2.0, phase: float = 0.0) -> SectionSpec:
    """Rolling ground that crosses a flat template several times, so one
    section has several separate cut zones and fill zones."""
    xs = np.arange(-140, 141, 10.0)
    g = [(float(x), float(elev + amp * np.sin((x + phase) / 9.0))) for x in xs]
    d = [(-62, elev - 1.5), (-56, elev), (0, elev + 1.12), (56, elev), (62, elev - 1.5)]   # 2 % crown
    return SectionSpec(station, g, d)


def zones(spec: SectionSpec) -> tuple[int, int]:
    """Number of separate fill zones and cut zones in a section."""
    x0 = max(spec.ground[0][0], spec.design[0][0])
    x1 = min(spec.ground[-1][0], spec.design[-1][0])
    x = np.linspace(x0, x1, 20001)
    sign = np.sign(_interp(spec.design, x) - _interp(spec.ground, x))
    runs = [v for i, v in enumerate(sign) if v != 0 and (i == 0 or sign[i - 1] != v)]
    return runs.count(1.0), runs.count(-1.0)


def _draw_section(page: fitz.Page, spec: SectionSpec, y_axis: float, x_c: float,
                  elev0: float, n_squares: int) -> None:
    sx = lambda off: x_c + off * PT_PER_FT
    sy = lambda el: y_axis - (el - elev0) * PT_PER_FT
    top = y_axis - n_squares * GRID_FT * PT_PER_FT
    left, right = sx(-140), sx(140)
    shape = page.new_shape()
    for off in np.arange(-140, 141, GRID_FT):                      # vertical grid
        shape.draw_line((sx(off), top), (sx(off), y_axis))
    for k in range(n_squares + 1):                                 # horizontal grid
        y = y_axis - k * GRID_FT * PT_PER_FT
        shape.draw_line((left, y), (right, y))
    shape.finish(width=0.48, color=(0, 0, 0), closePath=False)
    for off in np.arange(-140, 140, 1.0):                         # axis ticks
        if off % GRID_FT:
            shape.draw_line((sx(off), y_axis), (sx(off), y_axis - 1.6))
    shape.finish(width=0.24, color=(0, 0, 0), closePath=False)
    shape.draw_polyline([(sx(o), sy(e)) for o, e in spec.ground])  # existing ground: dashed
    shape.finish(width=0.84, color=(0, 0, 0), dashes="[2.52 1.44] 0", closePath=False)
    shape.draw_polyline([(sx(o), sy(e)) for o, e in spec.design])  # proposed design: solid
    shape.finish(width=0.6, color=(0, 0, 0), closePath=False)
    shape.commit()
    for off in range(-140, 141, 10):
        page.insert_text((sx(off) - 6, y_axis + 9), str(off), fontsize=6)
    for k in range(n_squares + 1):
        page.insert_text((right + 4, y_axis - k * GRID_FT * PT_PER_FT + 2), str(int(elev0 + k * GRID_FT)), fontsize=6)
    page.insert_text((sx(118), y_axis - 0.8 * GRID_FT * PT_PER_FT), spec.station, fontsize=11)


def make_pdf(path: str, pages: list[list[SectionSpec]], scanned: bool = False, dpi: int = 254) -> None:
    """Stack the sections of each inner list on one 17x11 in sheet, highest
    station at the top (the usual convention)."""
    doc = fitz.open()
    for specs in pages:
        page = doc.new_page(width=1224, height=792)
        n_squares = 4
        y = 120.0
        for spec in specs:
            y_axis = y + n_squares * GRID_FT * PT_PER_FT
            elev0 = 10 * np.floor(min(e for _, e in spec.ground + spec.design) / 10) - 10
            _draw_section(page, spec, y_axis, 612, elev0, n_squares)
            y = y_axis + 40
    if scanned:
        out = fitz.open()
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            p2 = out.new_page(width=page.rect.width, height=page.rect.height)
            p2.insert_image(p2.rect, pixmap=pix)
        out.save(path)
    else:
        doc.save(path)
