"""Pictures to check the takeoff against: each section's audit overlay and
traced lines, and whole sheets of the original PDF with their sections."""
from __future__ import annotations

import os

import pymupdf as fitz
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from . import jobs
from .jobs import Job

router = APIRouter()

CACHED = {"Cache-Control": "private, max-age=86400"}     # a job's pictures never change
PAGE_PX = 2400          # longest side of a rendered sheet image
PAGE_CACHE = 12         # rendered sheets kept per job


def _section(job: Job, n: int):
    if job.result is None or not 0 <= n < len(job.result.sections):
        raise HTTPException(404, "No such section.")
    return job.result.sections[n]


@router.get("/api/jobs/{job_id}/sections/{n}.png")
def section_png(job_id: str, n: int):
    png = _section(jobs.get_job(job_id), n).overlay_png
    if not png:
        raise HTTPException(404, "No overlay for this section.")
    return Response(png, media_type="image/png", headers=CACHED)


@router.get("/api/jobs/{job_id}/sections/{n}/profile.json")
def section_profile(job_id: str, n: int):
    prof = _section(jobs.get_job(job_id), n).profile
    if prof is None:
        raise HTTPException(404, "No profile for this section.")
    return JSONResponse(prof, headers=CACHED)


def _sheet(job: Job, n: int) -> fitz.Page:
    if job.result is None or not job.pdf_path or not os.path.exists(job.pdf_path):
        raise HTTPException(404, "The original PDF is no longer available for this job.")
    doc = fitz.open(job.pdf_path)
    if not 1 <= n <= len(doc):
        doc.close()
        raise HTTPException(404, "No such page.")
    return doc[n - 1]


@router.get("/api/jobs/{job_id}/pages/{n}.png")
def page_png(job_id: str, n: int):
    """The original sheet as an image, as it is displayed (rotation applied)."""
    job = jobs.get_job(job_id)
    png = job.pages.get(n)
    if png is None:
        page = _sheet(job, n)
        z = PAGE_PX / max(page.rect.width, page.rect.height)
        png = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False).tobytes("png")
        page.parent.close()
        with jobs.LOCK:
            if len(job.pages) >= PAGE_CACHE:
                job.pages.pop(next(iter(job.pages)))
            job.pages[n] = png
    return Response(png, media_type="image/png", headers=CACHED)


@router.get("/api/jobs/{job_id}/pages/{n}.json")
def page_sections(job_id: str, n: int):
    """Every measured cross-section on a sheet, in the sheet image's own
    coordinates (PDF points, as displayed): its frame corners, the traced
    ground and proposed surfaces, and where its section image sits -- so the
    app can shade cut / fill and outline each section on the whole sheet."""
    job = jobs.get_job(job_id)
    page = _sheet(job, n)
    rot = page.rotation_matrix
    size = [round(page.rect.width, 2), round(page.rect.height, 2)]
    page.parent.close()
    pt = lambda p: None if p is None else [round(q, 1) for q in (fitz.Point(p) * rot)]
    thin = lambda line: [pt(p) for p in line[::2]]      # ~0.5 ft apart: plenty on a whole sheet
    out = []
    for i, s in enumerate(job.result.sections):
        g = s.geometry
        if s.page != n or not g:
            continue
        out.append({
            "id": i, "frame": [pt(p) for p in g["frame"]],
            "ground": thin(g["ground"]), "finished": thin(g["finished"]), "subgrade": thin(g["subgrade"]),
            "canvas": [pt(p) for p in g["canvas"]] if g.get("canvas") else None,
            "image_size": g.get("image_size"),
        })
    return JSONResponse({"page": n, "size": size, "image": f"/api/jobs/{job.id}/pages/{n}.png", "sections": out},
                        headers=CACHED)
