"""
The two deliverables of a finished job, built the same way for the app
(/api/jobs/{id}/calibration, /api/jobs/{id}/cross-sections) and for the
public API (/api/v1): the feet-to-pixel calibration of every sheet, and every
cross-section's left / right cut and fill with its shapes and confidence.
Their formats are in gdot_earthwork.calibration / .cross_sections and
backend/schemas.
"""
from __future__ import annotations

from fastapi import HTTPException

from gdot_earthwork import calibration as calib
from gdot_earthwork import cross_sections as xsec

from .jobs import Job, require_pdf
from .payload import section_sides, surface_of


def calibration_for(job: Job) -> dict:
    """Built once per job and kept: scale notes on scanned sheets are read by
    OCR, which takes a few seconds."""
    if job.status != "done" or job.result is None:
        raise HTTPException(409, "Job is not finished.")
    with job.build_lock:
        if job.calibration is None:
            roads = {r["id"]: r["label"] for r in job.payload["roads"]}
            labels = {s["id"]: roads.get(s["road"]) for s in job.payload["sections"]}
            job.calibration = calib.build(job.result, require_pdf(job), job.filename, labels)
    return job.calibration


def cross_sections_for(job: Job, surface: str | None = None) -> dict:
    """Built on every request, so it always carries the latest hand edits."""
    cal = calibration_for(job)
    sf = surface_of(job.payload, surface)
    measured = lambda sec, s: sec["sides_measured"][s] if sec.get("sides_measured") else None
    return xsec.build(job.payload, cal, sf, section_sides, measured)
