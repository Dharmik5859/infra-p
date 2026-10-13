"""The app's calibration and cross-section endpoints. The public API serves
the same JSON (api.results) under /api/v1."""
from __future__ import annotations

from fastapi import APIRouter

from . import jobs, results

router = APIRouter()


@router.get("/api/jobs/{job_id}/calibration")
def calibration(job_id: str):
    """Feet-to-pixel calibration for every sheet of the plan set, and the cut /
    fill areas found on each as page-space shapes (see gdot_earthwork.calibration
    for the format). Built once per job: scale notes on scanned sheets are read
    by OCR, which takes a few seconds."""
    return results.calibration_for(jobs.get_job(job_id))


@router.get("/api/jobs/{job_id}/cross-sections")
def cross_sections(job_id: str, surface: str | None = None):
    """Every cross-section in the received cross-section format (see
    gdot_earthwork.cross_sections): station, street, stage, left / right cut
    and fill (hand edits applied), its shapes on the page, its confidence
    score and alerts below the pass score."""
    return results.cross_sections_for(jobs.get_job(job_id), surface)
