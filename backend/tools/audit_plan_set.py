"""Audit a plan set end to end, for reviewing the pipeline where there is no
reference answer.

    python -m tools.audit_plan_set PLANS.pdf OUT_DIR [--raster-check] [--pages 1-20]

Writes to OUT_DIR:

  summary.json          per section: page, position, station (+ how read), fill / cut
                        and left / right, why 0 / 0, warnings, confidence, scale read
  calibration.json      GET /api/jobs/{id}/calibration for this plan set
  cross_sections.json   GET /api/jobs/{id}/cross-sections for this plan set
  overlays/pP_I.png     each section as traced (ground blue, finished black,
                        subgrade yellow, fill green, cut red)
  sheets/pP_I.png       the same section cropped from the original sheet

--raster-check measures every CAD (vector) section a second time from its
rendered pixels (the scan path) and records both answers side by side
(summary.json "raster"): two independent readings of the same drawing.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time

import pymupdf as fitz

import main
from gdot_earthwork import calibration as calib
from gdot_earthwork import cross_sections as xsec
from gdot_earthwork.config import get_config
from gdot_earthwork.plan_set import process_plan_set


def _pages(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def audit(pdf: str, out: str, raster_check: bool = False, pages: list[int] | None = None) -> dict:
    os.makedirs(os.path.join(out, "overlays"), exist_ok=True)
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)
    t = time.time()
    res = process_plan_set(pdf, overlays=True, pages=pages)
    seconds = round(time.time() - t, 1)
    job = main.Job(id="audit", filename=os.path.basename(pdf))
    payload = main.serialize(job, res)
    roads = {r["id"]: r["label"] for r in payload["roads"]}
    labels = {s["id"]: roads.get(s["road"]) for s in payload["sections"]}
    cal = calib.build(res, pdf, job.filename, labels)
    measured = lambda sec, sf: sec["sides_measured"][sf] if sec.get("sides_measured") else None
    xs = xsec.build(payload, cal, res.design_surface, main.section_sides, measured)

    raster = {}
    if raster_check and any(s.page_kind == "vector" for s in res.sections):
        cfg = dataclasses.replace(get_config(), force_raster=True)
        vec_pages = sorted({s.page for s in res.sections if s.page_kind == "vector"})
        rr = process_plan_set(pdf, cfg=cfg, overlays=False, pages=vec_pages)
        for s in rr.sections:
            raster[(s.page, s.index)] = s

    doc = fitz.open(pdf)
    rows = []
    for i, s in enumerate(res.sections):
        if s.overlay_png:
            with open(os.path.join(out, "overlays", f"p{s.page}_{s.index}.png"), "wb") as f:
                f.write(s.overlay_png)
        if s.geometry:
            page = doc[s.page - 1]
            pts = [fitz.Point(p) * page.rotation_matrix for p in s.geometry["frame"]]
            xs_, ys_ = [p.x for p in pts], [p.y for p in pts]
            clip = fitz.Rect(min(xs_) - 4, min(ys_) - 24, max(xs_) + 4, max(ys_) + 24) * page.derotation_matrix
            page.get_pixmap(clip=clip, dpi=110).save(os.path.join(out, "sheets", f"p{s.page}_{s.index}.png"))
        sec = payload["sections"][i]
        row = {
            "id": i, "page": s.page, "index": s.index, "station": s.station_label, "stationSource": s.label_source,
            "road": roads.get(sec["road"]), "kind": s.page_kind, "method": s.method,
            "fill": s.fill_ft2, "cut": s.cut_ft2, "altFill": s.alt_fill_ft2, "altCut": s.alt_cut_ft2,
            "sides": (s.sides or {}).get(res.design_surface), "zeroReason": s.zero_reason,
            "centre": s.centre_source, "scale": s.scale, "confidence": (s.confidence or {}).get("score"),
            "warnings": s.warnings,
        }
        r = raster.get((s.page, s.index))
        if r is not None:
            row["raster"] = {"fill": r.fill_ft2, "cut": r.cut_ft2, "station": r.station_label}
        rows.append(row)
    doc.close()

    summary = {
        "file": os.path.basename(pdf), "pages": res.pages, "crossSectionPages": res.cross_section_pages,
        "sections": len(res.sections), "seconds": seconds, "kinds": sorted({s.page_kind for s in res.sections}),
        "roads": [{"label": r["label"], "from": r["station_from"], "to": r["station_to"], "sections": len(r["sections"]),
                   "fill_cy": r["volumes"][res.design_surface]["fill_cy"],
                   "cut_cy": r["volumes"][res.design_surface]["cut_cy"]} for r in payload["roads"]],
        "warnings": res.warnings, "lowConfidence": payload["summary"]["low_confidence"],
        "calibration": {"calibrated": len(cal["calibrations"]), "uncalibrated": cal["uncalibratedPages"],
                        "documentScale": cal["documentScale"],
                        "noteChecks": [{"page": c["pageNumber"], "grid": c["pixelLengthX"],
                                        "note": c["noteCheck"]["pixelLengthX"], "text": c["noteCheck"]["text"]}
                                       for c in cal["calibrations"] if c.get("noteCheck")]},
        "rows": rows,
    }
    for name, value in (("summary.json", summary), ("calibration.json", cal), ("cross_sections.json", xs)):
        with open(os.path.join(out, name), "w") as f:
            json.dump(value, f, indent=1, default=str)
    return summary


if __name__ == "__main__":
    args = sys.argv[1:]
    raster_check = "--raster-check" in args
    pages = None
    if "--pages" in args:
        j = args.index("--pages")
        pages = _pages(args[j + 1])
        args = args[:j] + args[j + 2:]
    args = [a for a in args if a != "--raster-check"]
    s = audit(args[0], args[1], raster_check, pages)
    print(f"{s['file']}: {s['sections']} sections on {s['crossSectionPages']}/{s['pages']} pages in {s['seconds']}s, "
          f"{len(s['roads'])} roads, {s['lowConfidence']} below 85 %")
