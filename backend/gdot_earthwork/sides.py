"""
Left / right of the centreline.

Earthwork is reported per side of the alignment's centreline (offset 0):
left fill, left cut, right fill, right cut. The centreline is read from each
section's offset-axis labels (frames.find_centreline); the measured areas
are split there from 1 ft strips (surfaces.area_strips).

Hand edits keep their side: an area the user outlines is split at the
centreline; an area they remove comes off the side it lies on; a typed total
stretches the traced zones on both sides alike (the same rule that draws the
shading), so the four numbers always add up to the totals in use.
"""
from __future__ import annotations

SIDES = ("left", "right")
KINDS = ("fill", "cut")


def split_strips(strips, centre_ft: float) -> tuple[float, float]:
    """Sum of 1 ft strips left and right of `centre_ft` (ft from the frame's left edge)."""
    c = max(0.0, min(float(len(strips)), centre_ft))
    i = int(c)
    left = float(sum(strips[:i]))
    if i < len(strips):
        left += float(strips[i]) * (c - i)
    return left, float(sum(strips)) - left


def measured_sides(fill_strips, cut_strips, centre_ft: float) -> dict:
    lf, rf = split_strips(fill_strips, centre_ft)
    lc, rc = split_strips(cut_strips, centre_ft)
    r2 = lambda v: round(v, 2)
    return {"left": {"fill_ft2": r2(lf), "cut_ft2": r2(lc)}, "right": {"fill_ft2": r2(rf), "cut_ft2": r2(rc)}}


def _clip(poly, x: float, keep_left: bool):
    """Sutherland-Hodgman: the part of a polygon on one side of the line X = x."""
    inside = (lambda p: p[0] <= x) if keep_left else (lambda p: p[0] >= x)
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(_cross(prev, cur, x))
            out.append(cur)
        elif inside(prev):
            out.append(_cross(prev, cur, x))
    return out


def _cross(a, b, x):
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _area(poly) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))) / 2 if len(poly) > 2 else 0.0


def polygon_sides(pts, centre_x: float) -> tuple[float, float]:
    """Area (in the polygon's units²) left and right of x = centre_x."""
    poly = [tuple(p) for p in pts]
    return _area(_clip(poly, centre_x, True)), _area(_clip(poly, centre_x, False))


def _spans_at(poly, x):
    ys = []
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (x1 <= x < x2) or (x2 <= x < x1):
            ys.append(y1 + (x - x1) / (x2 - x1) * (y2 - y1))
    ys.sort()
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]


def removal_sides(profile: dict, surface: str, kind: str, pts, centre_x: float) -> tuple[float, float]:
    """How the traced fill (or cut) inside an outline divides between the sides:
    the shares (adding to 1) of it lying left and right of the centreline,
    column by column as areas are measured."""
    g, t = profile["ground"], profile.get(surface) or profile["finished"]
    inside = [0.0, 0.0]
    for x, gi, ti in zip(profile["x"], g, t):
        if gi is None or ti is None:
            continue
        a, b = (ti, gi) if kind == "fill" else (gi, ti)
        if b - a <= 0.05:
            continue
        for c, d in _spans_at(pts, x):
            inside[0 if x < centre_x else 1] += max(0.0, min(b, d) - max(a, c))
    tot = sum(inside)
    return (inside[0] / tot, inside[1] / tot) if tot else (0.5, 0.5)


def current_sides(measured: dict, measured_total: dict, area: dict, marks: list[dict]) -> dict:
    """Left / right fill and cut for the areas in use.

    measured        {"left": {"fill_ft2", "cut_ft2"}, "right": {...}} as traced
    measured_total  {"fill_ft2", "cut_ft2"} as traced
    area            {"fill_ft2", "cut_ft2"} in use (measured or edited)
    marks           outlined / removed areas, each with "sides": {"left": ft², "right": ft²}

    Returns the same shape as `measured`, plus "unplaced" {"fill_ft2", "cut_ft2"}:
    area typed in where the drawing has no zone of that kind to put it on."""
    out = {s: {} for s in SIDES}
    unplaced = {}
    for kind in KINDS:
        key = f"{kind}_ft2"
        added = [m for m in marks if m["kind"] == kind]
        removed = [m for m in marks if m["kind"] == f"remove_{kind}"]
        base = max(0.0, area[key] - sum(m["ft2"] for m in added))
        left_over = measured_total[key] - sum(m["ft2"] for m in removed)
        k = (base / left_over if left_over > 0.005 else 0.0) if measured_total[key] > 0 else None
        unplaced[key] = round(base, 2) if k is None else 0.0
        for side in SIDES:
            traced = measured[side][key] - sum(m["sides"][side] for m in removed)
            v = max(0.0, traced) * (k or 0.0) + sum(m["sides"][side] for m in added)
            out[side][key] = round(v, 2)
    out["unplaced"] = unplaced
    return out
