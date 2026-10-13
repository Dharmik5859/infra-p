"""Comparisons with results provided for the same plan set (uploaded, or
stored in backend/comparisons, e.g. SR 5), and the JSON Schemas of the
calibration and cross-section responses."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from gdot_earthwork.compare import compare as compare_reference, read_reference

from . import jobs, schemas, settings
from .payload import section_sides, surface_of

router = APIRouter()

MAX_REFERENCE_MB = 20


@router.post("/api/jobs/{job_id}/compare")
async def compare_job(job_id: str, file: UploadFile = File(...), surface: str | None = None):
    """Compare the job's sections (hand edits included) with results provided
    for the same plan set: an xlsx / csv with Street | Stage | Station |
    Delta | Left / Right cut and fill areas and volumes (see
    gdot_earthwork.compare)."""
    job = jobs.require_finished(jobs.get_job(job_id))
    data = await file.read(MAX_REFERENCE_MB * 2 ** 20 + 1)
    if len(data) > MAX_REFERENCE_MB * 2 ** 20:
        raise HTTPException(413, f"Results files are limited to {MAX_REFERENCE_MB} MB.")
    try:
        reference = read_reference(data, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Could not read the results file: {e}") from None
    sf = surface_of(job.payload, surface)
    report = compare_reference(job.payload["sections"], reference, sf, section_sides)
    report.update(title=f"{job.filename} vs {file.filename}", planSet=job.filename, referenceFile=file.filename)
    return report


def _comparison_files() -> list[str]:
    if not os.path.isdir(settings.COMPARISONS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(settings.COMPARISONS_DIR) if f.endswith(".json"))


@router.get("/api/comparisons")
def comparisons():
    out = []
    for name in _comparison_files():
        with open(os.path.join(settings.COMPARISONS_DIR, name + ".json")) as f:
            r = json.load(f)
        out.append({"name": name, "title": r.get("title"), "planSet": r.get("planSet"),
                    "referenceFile": r.get("referenceFile"), "generated": r.get("generated"), "summary": r["summary"]})
    return out


@router.get("/api/comparisons/{name}")
def comparison(name: str):
    if name not in _comparison_files():
        raise HTTPException(404, "No such comparison.")
    return FileResponse(os.path.join(settings.COMPARISONS_DIR, name + ".json"), media_type="application/json")


@router.get("/api/schemas/{name}")
def schema(name: str):
    return schemas.response(name)
