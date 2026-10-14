"""
The cross-section response: every section of a processed plan set in the
app's received format -- its station, street and stage, cut / fill areas left
and right of the centreline, the cut / fill zones as page shapes (the Shapes
JSON of the calibration format), its confidence score and any alerts.

    {
      "document":      {fileName, pages, sections, surface},
      "units":         {area: "sqft", volume: "cy", pixel: ...},
      "passScore":     85,
      "summary":       {crossSections, passed, alerts},
      "calibrations":  [calibration per sheet ...],
      "crossSections": [{
          id: "xs-<n>", pageNumber, stationId, stationFt, streetName, stage,
          calibrationId,
          areas: {left: {cutSqFt, fillSqFt}, right: {...}, total: {cutSqFt, fillSqFt, netSqFt}},
          measuredAreas: {...same, as traced...}, edited,
          centreline: {source}, scale: {ftPerSquareX/Y, pixelsPerFootX/Y, sourceX/Y, ...},
          confidence: {score, passed, threshold, deductions},
          alerts: [{level, message, reasons}],
          shapes: [{crossSectionType, id, pageNumber, points, position2D, dimensions,
                    side, stage, stationId, streetName, areaSqFt, crossSectionId}]
      }],
      "shapes":  [...every shape, flat...],
      "alerts":  [{crossSectionId, pageNumber, stationId, score, level, message, reasons}]
    }

schemas/cross-sections.schema.json is the contract; tests validate every
response against it.
"""
from __future__ import annotations

from collections.abc import Callable


def _side_areas(sides: dict | None, total: dict) -> dict:
    out = {}
    for side in ("left", "right"):
        sd = (sides or {}).get(side)
        out[side] = {"cutSqFt": sd["cut_ft2"], "fillSqFt": sd["fill_ft2"]} if sd else None
    out["total"] = {"cutSqFt": total["cut_ft2"], "fillSqFt": total["fill_ft2"],
                    "netSqFt": round(total["fill_ft2"] - total["cut_ft2"], 2)}
    return out


def build(payload: dict, calibration: dict, surface: str,
          sides: Callable[[dict, str], dict | None], measured_sides: Callable[[dict, str], dict | None]) -> dict:
    """The response for a finished job: `payload` is the job's API result
    (edits applied), `calibration` its calibration response; `sides(sec,
    surface)` gives a section's current left / right areas and
    `measured_sides` the traced ones."""
    roads = {r["id"]: r["label"] for r in payload["roads"]}
    cal_of = {c["pageNumber"]: c["id"] for c in calibration["calibrations"]}
    shapes_of: dict[str, list] = {}
    for sh in calibration["shapes"]:
        shapes_of.setdefault(sh.get("crossSectionId"), []).append(sh)
    stage = next((sh["stage"] for sh in calibration["shapes"] if sh.get("stage")), None)
    edits = payload["edits"].get(surface, {})

    xs, alerts = [], []
    for s in payload["sections"]:
        xid = f"xs-{s['id']}"
        conf = s.get("confidence") or {}
        sec_alerts = conf.get("alerts", [])
        item = {
            "id": xid,
            "pageNumber": s["page"],
            "stationId": s["station"],
            "stationFt": s["station_ft"],
            "stationSource": s["label_source"],
            "streetName": roads.get(s["road"]) or s.get("street"),
            "stage": stage,
            "calibrationId": cal_of.get(s["page"]),
            "areas": _side_areas(sides(s, surface), s["areas"][surface]),
            "measuredAreas": _side_areas(measured_sides(s, surface), s["measured"][surface]),
            "edited": str(s["id"]) in edits,
            "centreline": {"source": s["centreline"]["source"]},
            "scale": s.get("scale"),
            "noEarthwork": s["zero_reason"],
            "confidence": {k: conf[k] for k in ("score", "passed", "threshold", "deductions") if k in conf},
            "alerts": sec_alerts,
            "warnings": s["warnings"],
            "shapes": shapes_of.get(xid, []),
        }
        xs.append(item)
        for a in sec_alerts:
            alerts.append({"crossSectionId": xid, "pageNumber": s["page"], "stationId": s["station"],
                           "score": conf.get("score"), **a})
    return {
        # areas are to `surface`; shapes are drawn to the design surface of the run
        "document": {**calibration["document"], "surface": surface,
                     "shapesSurface": calibration["document"]["surface"]},
        "units": {"area": "sqft", "volume": "cy", "pixel": calibration["pixelUnit"]},
        "passScore": next((x["confidence"]["threshold"] for x in xs if x["confidence"]), 85),
        "summary": {"crossSections": len(xs), "passed": sum(bool(x["confidence"].get("passed")) for x in xs),
                    "alerts": len(alerts)},
        "calibrations": calibration["calibrations"],
        "crossSections": xs,
        "shapes": [sh for x in xs for sh in x["shapes"]],
        "alerts": alerts,
    }
