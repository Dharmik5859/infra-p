"""
A job's result as the app reads it (the "payload"): sections, roads and
volumes for both surfaces, and the hand edits laid over the measurement.

serialize() builds it once from the pipeline's PlanSetResult; edits then
change a section's areas in place (the measured ones are kept beside them)
and every road's volumes are recomputed from whatever is in use.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException

from gdot_earthwork.plan_set import ZERO_REASONS, PlanSetResult
from gdot_earthwork.sides import current_sides, polygon_sides, removal_sides, road_side_volumes
from gdot_earthwork.volume import average_end_area_volume

if TYPE_CHECKING:
    from .jobs import Job


def rounded(v: float, n: int = 1) -> float:
    return round(float(v), n) + 0.0     # +0.0 turns -0.0 into 0.0


def _volume_json(vol) -> dict:
    return {
        "fill_cy": rounded(vol.total_fill_cy),
        "cut_cy": rounded(vol.total_cut_cy),
        "net_cy": rounded(vol.total_net_cy),
        "segments": [{
            "from": s.station_from, "to": s.station_to, "length_ft": rounded(s.length_ft, 2),
            "fill_cy": rounded(s.fill_cy), "cut_cy": rounded(s.cut_cy), "net_cy": rounded(s.net_cy),
            "warning": s.warning,
        } for s in vol.segments],
    }


def serialize(job: Job, res: PlanSetResult) -> dict:
    sec_id = {id(s): i for i, s in enumerate(res.sections)}
    road_of: dict[int, str] = {}
    roads = []
    alt_surface = "finished" if res.design_surface == "subgrade" else "subgrade"
    for r_i, (road, vol, alt) in enumerate(zip(res.roads, res.volumes, res.alt_volumes)):
        rid = f"r{r_i + 1}"
        for e in road.entries:
            road_of[sec_id[id(e.ref)]] = rid
        roads.append({
            "id": rid,
            "label": road.label,
            "station_from": road.entries[0].station_label,
            "station_to": road.entries[-1].station_label,
            "repeat_of": next((f"r{j + 1}" for j, o in enumerate(res.roads) if o.label == road.repeat_of), None),
            "flags": road.flags,
            "sections": [sec_id[id(e.ref)] for e in road.entries],
            "volumes": {res.design_surface: _volume_json(vol), alt_surface: _volume_json(alt)},
        })

    def areas(s):
        return {
            res.design_surface: {"fill_ft2": rounded(s.fill_ft2, 2), "cut_ft2": rounded(s.cut_ft2, 2)},
            alt_surface: {"fill_ft2": rounded(s.alt_fill_ft2, 2), "cut_ft2": rounded(s.alt_cut_ft2, 2)},
        }
    sections = [{
        "id": i,
        "page": s.page,
        "station": s.station_label,
        "station_ft": s.station_ft,
        "label_source": s.label_source,
        "areas": areas(s),               # what volumes use: measured, or the user's edit
        "measured": areas(s),            # as traced from the drawing, never changed
        "marks": {res.design_surface: [], alt_surface: []},   # areas the user outlined on the image
        "zero_reason": s.zero_reason,
        # left / right of the centreline, as traced; marks carry their own split
        "sides_measured": {sf: s.sides[sf] for sf in (res.design_surface, alt_surface)} if s.sides else None,
        "centreline": {
            "source": s.centre_source,
            "x": round(s.centre_ft * s.overlay_px_per_ft, 1)          # in the section image's pixels
            if s.centre_ft is not None and s.overlay_px_per_ft else None,
        },
        "method": s.method,
        "page_kind": s.page_kind,
        # ft per grid square on each axis, as read off the axis labels (stages.calibrate)
        "scale": s.scale,
        # 0-100, with what lowered it; below the pass score it carries alerts
        "confidence": s.confidence,
        "road": road_of.get(i),
        "street": s.street,              # as printed in the sheet's title block
        "warnings": s.warnings,
        "overlay": f"/api/jobs/{job.id}/sections/{i}.png" if s.overlay_png else None,
        "overlay_px_per_ft": s.overlay_px_per_ft,
        "profile": f"/api/jobs/{job.id}/sections/{i}/profile.json" if s.profile else None,
    } for i, s in enumerate(res.sections)]
    return {
        "job_id": job.id,
        "filename": job.filename,
        "summary": {
            "pages": res.pages,
            "cross_section_pages": res.cross_section_pages,
            "sections": len(res.sections),
            "roads": len(roads),
            "seconds": res.timing["total_seconds"],
            "page_kinds": sorted({s.page_kind for s in res.sections}),
            "design_surface": res.design_surface,
            "surfaces": [res.design_surface, alt_surface],
            "no_earthwork": sum(s.zero_reason is not None for s in res.sections),
            "low_confidence": sum(1 for s in res.sections if s.confidence and not s.confidence["passed"]),
        },
        "zero_reasons": ZERO_REASONS,
        "roads": roads,
        "sections": sections,
        "warnings": res.warnings,
        "edits": {res.design_surface: {}, alt_surface: {}},   # section id -> {fill_ft2, cut_ft2}
    }


def surface_of(payload: dict, surface: str | None) -> str:
    """The surface asked for (the design surface when none is), checked."""
    surfaces = payload["summary"]["surfaces"]
    surface = surface or surfaces[0]
    if surface not in surfaces:
        raise HTTPException(400, f"surface must be one of {surfaces}")
    return surface


def section_sides(sec: dict, surface: str) -> dict | None:
    """Left / right fill and cut of a section (API payload) for the areas in use."""
    if not sec.get("sides_measured"):
        return None
    return current_sides(sec["sides_measured"][surface], sec["measured"][surface], sec["areas"][surface],
                         sec.get("marks", {}).get(surface, []))


def road_sides(payload: dict, road: dict, surface: str) -> dict | None:
    """Left / right volumes of a road (API payload) for the areas in use."""
    secs = [payload["sections"][i] for i in road["sections"]]
    stations = [(s["station_ft"], section_sides(s, surface)) for s in secs if s["station_ft"] is not None]
    if not stations or any(sd is None for _, sd in stations):
        return None
    return road_side_volumes(stations)


@dataclass
class _Station:
    station_label: str
    station_ft: float
    fill_ft2: float
    cut_ft2: float


def recompute_volumes(payload: dict, surface: str) -> None:
    """Rebuild every road's average-end-area volumes for `surface` from the
    sections' current (possibly edited) areas."""
    secs = payload["sections"]
    for road in payload["roads"]:
        stations = [_Station(secs[i]["station"], secs[i]["station_ft"], **secs[i]["areas"][surface])
                    for i in road["sections"] if secs[i]["station_ft"] is not None]
        road["volumes"][surface] = _volume_json(average_end_area_volume(stations, road["label"]))


# ---------------------------------------------------------------- hand edits
MAX_AREA_FT2 = 1e6
MAX_MARKS, MAX_MARK_POINTS = 50, 500
MARK_KINDS = ("fill", "cut", "remove_fill", "remove_cut")


def parse_area(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= MAX_AREA_FT2:
        raise HTTPException(400, f"Areas must be numbers between 0 and {MAX_AREA_FT2:g} sq ft.")
    return rounded(v, 2)


def parse_marks(val, sec, measured: dict, surface: str) -> list[dict]:
    """Areas the user outlined on the section image: [{kind, pts}], pts in
    image pixels. fill / cut add the outlined area (measured here from the
    image scale); remove_fill / remove_cut take away the traced area inside
    the outline -- the browser measures that share of the traced zones and
    sends it as ft2, kept within what was measured."""
    if val is None:
        return []
    ppf, prof = sec.overlay_px_per_ft, sec.profile
    if not isinstance(val, list) or len(val) > MAX_MARKS or not ppf or not prof:
        raise HTTPException(400, f"marks must be a list of at most {MAX_MARKS} outlined areas.")
    w, h = prof["size"]
    out = []
    for m in val:
        pts = m.get("pts") if isinstance(m, dict) else None
        if m.get("kind") not in MARK_KINDS or not isinstance(pts, list) or not 3 <= len(pts) <= MAX_MARK_POINTS:
            raise HTTPException(400, f"Each mark needs a kind ({'|'.join(MARK_KINDS)}) and 3 to {MAX_MARK_POINTS} points.")
        clean = []
        for p in pts:
            if (not isinstance(p, list) or len(p) != 2
                    or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in p)):
                raise HTTPException(400, "Mark points must be [x, y] pixel pairs.")
            clean.append([round(min(max(p[0], 0), w), 1), round(min(max(p[1], 0), h), 1)])
        a = 0.0
        for (x1, y1), (x2, y2) in zip(clean, clean[1:] + clean[:1]):
            a += x1 * y2 - x2 * y1
        cx = sec.centre_ft * ppf if sec.centre_ft is not None else w / 2
        if m["kind"].startswith("remove_"):
            base = m["kind"][len("remove_"):]
            ft2 = min(parse_area(m.get("ft2")), measured[f"{base}_ft2"])
            sl, sr = removal_sides(prof, surface, base, clean, cx)
            left, right = ft2 * sl, ft2 * sr
        else:
            ft2 = abs(a) / 2 / ppf ** 2
            left, right = (v / ppf ** 2 for v in polygon_sides(clean, cx))
        out.append({"kind": m["kind"], "pts": clean, "ft2": rounded(ft2, 2),
                    "sides": {"left": rounded(left, 2), "right": rounded(right, 2)}})
    for kind in ("fill", "cut"):
        if sum(m["ft2"] for m in out if m["kind"] == f"remove_{kind}") > measured[f"{kind}_ft2"] + 0.05:
            raise HTTPException(400, f"Removed {kind} is more than the measured {kind}.")
    return out


def parse_edits(job: Job, body: dict) -> tuple[str, dict[int, dict | None]]:
    """Check an edits request (see PUT /api/jobs/{id}/edits) against the job:
    its surface and, per section, the new areas and marks or None (= back to
    measured). Nothing is changed yet, so a bad entry rejects the whole request."""
    payload = job.payload
    surface = surface_of(payload, body.get("surface"))
    edits = body.get("edits")
    if not isinstance(edits, dict) or len(edits) > len(payload["sections"]):
        raise HTTPException(400, "edits must map section ids to {fill_ft2, cut_ft2} or null.")
    parsed: dict[int, dict | None] = {}
    for key, val in edits.items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Unknown section {key!r}.") from None
        if not 0 <= i < len(payload["sections"]):
            raise HTTPException(400, f"Unknown section {key!r}.")
        if val is None:
            parsed[i] = None
        elif isinstance(val, dict):
            parsed[i] = {"fill_ft2": parse_area(val.get("fill_ft2")), "cut_ft2": parse_area(val.get("cut_ft2")),
                         "marks": parse_marks(val.get("marks"), job.result.sections[i],
                                              payload["sections"][i]["measured"][surface], surface)}
        else:
            raise HTTPException(400, f"Section {key}: expected {{fill_ft2, cut_ft2}} or null.")
    return surface, parsed


def apply_edits(payload: dict, surface: str, parsed: dict[int, dict | None]) -> None:
    """Lay parsed edits over the payload and recompute that surface's volumes.
    An edit equal to the measurement (and with no marks) is dropped, so the
    section reads as unedited again."""
    saved = payload["edits"][surface]
    for i, val in parsed.items():
        sec = payload["sections"][i]
        marks = val.pop("marks") if val else []
        sec.setdefault("marks", {})[surface] = marks
        if val is None or (val == sec["measured"][surface] and not marks):
            saved.pop(str(i), None)
            sec["areas"][surface] = dict(sec["measured"][surface])
        else:
            saved[str(i)] = val
            sec["areas"][surface] = dict(val)
    recompute_volumes(payload, surface)
