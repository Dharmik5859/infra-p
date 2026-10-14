"""Downloads: the volume and section tables as CSV, and the original PDF with
the takeoff drawn on it. All of them use the areas in use (hand edits
included) and say where edits were made."""
from __future__ import annotations

import csv
import io
import json
import os

from fastapi import APIRouter, Query
from fastapi.responses import Response

from gdot_earthwork.export import annotated_pdf

from . import jobs
from .payload import road_sides, rounded, section_sides, surface_of

router = APIRouter()

CENTRE_TEXT = {"text": "read from the drawing", "scan": "read from the scan", "neighbour": "from the neighbouring section",
               "assumed": "assumed at grid middle"}


def _csv(rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/jobs/{job_id}/volumes.csv")
def volumes_csv(job_id: str, exclude: list[str] = Query(default=[]), surface: str | None = None):
    job = jobs.require_finished(jobs.get_job(job_id))
    surface = surface_of(job.payload, surface)
    n_edited = len(job.payload["edits"][surface])
    title = f"Measured to {surface}" + (f"; {n_edited} section(s) edited by hand" if n_edited else "")
    rows = [[title], ["Road", "From", "To", "Length (ft)", "Fill (cy)", "Cut (cy)", "Net (cy)",
                      "Left fill (cy)", "Left cut (cy)", "Right fill (cy)", "Right cut (cy)", "Note"]]
    side_cells = lambda d: [d["left"]["fill_cy"], d["left"]["cut_cy"], d["right"]["fill_cy"], d["right"]["cut_cy"]] \
        if d else ["", "", "", ""]
    tf = tc = 0.0
    all_sides = {"left": {"fill_cy": 0.0, "cut_cy": 0.0}, "right": {"fill_cy": 0.0, "cut_cy": 0.0}}
    for r in job.payload["roads"]:
        if r["id"] in exclude:
            continue
        v = r["volumes"][surface]
        sides = road_sides(job.payload, r, surface)
        for i, s in enumerate(v["segments"]):
            rows.append([r["label"], s["from"], s["to"], s["length_ft"], s["fill_cy"], s["cut_cy"], s["net_cy"],
                         *side_cells(sides["segments"][i] if sides else None), s["warning"] or ""])
        rows.append([r["label"], "TOTAL", "", "", v["fill_cy"], v["cut_cy"], v["net_cy"], *side_cells(sides),
                     "; ".join(r["flags"])])
        tf, tc = tf + v["fill_cy"], tc + v["cut_cy"]
        for side in ("left", "right"):
            for k in ("fill_cy", "cut_cy"):
                all_sides[side][k] += sides[side][k] if sides else 0.0
    for side in all_sides.values():
        for k in side:
            side[k] = rounded(side[k])
    rows.append(["ALL ROADS", "", "", "", rounded(tf), rounded(tc), rounded(tf - tc), *side_cells(all_sides), ""])
    return _csv(rows, f"{os.path.splitext(job.filename)[0]}-volumes-{surface}.csv")


@router.get("/api/jobs/{job_id}/sections.csv")
def sections_csv(job_id: str):
    job = jobs.require_finished(jobs.get_job(job_id))
    roads = {r["id"]: r["label"] for r in job.payload["roads"]}
    a, b = job.payload["summary"]["surfaces"]
    edits = job.payload["edits"]
    rows = [["Page", "Station", "Station source", "Road",
             f"Fill to {a} (sq ft)", f"Cut to {a} (sq ft)",
             f"Left fill to {a} (sq ft)", f"Left cut to {a} (sq ft)",
             f"Right fill to {a} (sq ft)", f"Right cut to {a} (sq ft)",
             f"Fill to {b} (sq ft)", f"Cut to {b} (sq ft)",
             f"Left fill to {b} (sq ft)", f"Left cut to {b} (sq ft)",
             f"Right fill to {b} (sq ft)", f"Right cut to {b} (sq ft)",
             "Centreline", "Edited by hand", "Method", "Confidence (%)", "Alerts", "Warnings"]]
    for s in job.payload["sections"]:
        edited = [sf for sf in (a, b) if str(s["id"]) in edits[sf]]
        note = "; ".join(f"{sf} (measured fill {s['measured'][sf]['fill_ft2']}, cut {s['measured'][sf]['cut_ft2']})"
                         for sf in edited)

        def cells(sf, s=s):
            out, sd = [s["areas"][sf]["fill_ft2"], s["areas"][sf]["cut_ft2"]], section_sides(s, sf)
            for side in ("left", "right"):
                out += [sd[side]["fill_ft2"], sd[side]["cut_ft2"]] if sd else ["", ""]
            return out
        confidence = s.get("confidence") or {}
        rows.append([s["page"], s["station"] or "", s["label_source"] or "", roads.get(s["road"], ""),
                     *cells(a), *cells(b), CENTRE_TEXT.get(s["centreline"]["source"], ""),
                     note, s["method"], confidence.get("score", ""),
                     " | ".join(alert["message"] for alert in confidence.get("alerts", [])),
                     " | ".join(s["warnings"])])
    return _csv(rows, f"{os.path.splitext(job.filename)[0]}-sections.csv")


@router.get("/api/jobs/{job_id}/annotated.pdf")
def annotated(job_id: str, exclude: list[str] = Query(default=[]), surface: str | None = None):
    """The uploaded PDF, every page as it was, with each measured section's
    cut/fill shading and areas (hand edits included) drawn on it, plus
    summary pages at the end."""
    job = jobs.require_finished(jobs.get_job(job_id))
    pdf_path = jobs.require_pdf(job)
    surface = surface_of(job.payload, surface)
    with jobs.LOCK:
        payload = json.loads(json.dumps(job.payload))      # a consistent snapshot of the edits
    pdf = annotated_pdf(pdf_path, [s.geometry for s in job.result.sections], payload, surface, set(exclude))
    name = f"{os.path.splitext(job.filename)[0]}-takeoff.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
