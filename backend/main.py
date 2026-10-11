"""
HTTP API for the earthwork pipeline.

    GET  /api/health                         dependency check
    GET  /api/accuracy                       measured accuracy per plan-set format
    POST /api/jobs                           upload a plan-set PDF -> {job_id}
    GET  /api/jobs/{id}                      status, progress, and (when done) the result
    GET  /api/jobs/{id}/sections/{n}.png     audit overlay for one cross-section
    GET  /api/jobs/{id}/volumes.csv          volume table (respects ?exclude=road ids)
    GET  /api/jobs/{id}/sections.csv         per-section areas
    GET  /api/jobs/{id}/annotated.pdf        the original PDF with the takeoff drawn on it
    PUT  /api/jobs/{id}/edits                save hand-edited cut/fill areas; volumes are recomputed

Processing a plan set takes seconds to minutes, so uploads return at once
and the client polls the job. Jobs run MAX_CONCURRENT_JOBS at a time (each
already uses every core); the rest wait as "queued". Jobs live in memory and
expire after JOB_TTL_SECONDS; nothing is written to disk except the upload
itself, which is kept while its job lives (for the annotated PDF export) and
deleted with it.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from gdot_earthwork import __version__
from gdot_earthwork.export import annotated_pdf
from gdot_earthwork.plan_set import ZERO_REASONS, PlanSetResult, process_plan_set
from gdot_earthwork.volume import average_end_area_volume

JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", 6 * 3600))
# each job already runs its pages in parallel on all cores; more jobs at once
# would only slow every one of them down, so further uploads wait their turn
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", 1))
# Scanned plan sets are big (the dataset's largest is ~120 MB); the cap only
# guards the disk. Anything in front of the app (nginx, a load balancer, a
# hosting platform) must allow at least this much too -- see README.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 2048))
ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]

app = FastAPI(title="Earthwork Takeoff API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)


@dataclass
class Job:
    id: str
    filename: str
    created: float = field(default_factory=time.time)
    status: str = "queued"            # queued | running | done | error
    done: int = 0
    total: int = 0
    error: str | None = None
    result: PlanSetResult | None = None
    payload: dict | None = None
    pdf_path: str | None = None       # the upload, kept while the job lives


JOBS: dict[str, Job] = {}
LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)


def _expire() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with LOCK:
        for k in [k for k, j in JOBS.items() if j.created < cutoff and j.status in ("done", "error")]:
            job = JOBS.pop(k)
            if job.pdf_path:
                shutil.rmtree(os.path.dirname(job.pdf_path), ignore_errors=True)


def _round(v: float, n: int = 1) -> float:
    return round(float(v), n) + 0.0     # +0.0 turns -0.0 into 0.0


def serialize(job: Job, res: PlanSetResult) -> dict:
    sec_id = {id(s): i for i, s in enumerate(res.sections)}
    road_of: dict[int, str] = {}
    roads = []
    def vol_json(vol):
        return {
            "fill_cy": _round(vol.total_fill_cy),
            "cut_cy": _round(vol.total_cut_cy),
            "net_cy": _round(vol.total_net_cy),
            "segments": [{
                "from": s.station_from, "to": s.station_to, "length_ft": _round(s.length_ft, 2),
                "fill_cy": _round(s.fill_cy), "cut_cy": _round(s.cut_cy), "net_cy": _round(s.net_cy),
                "warning": s.warning,
            } for s in vol.segments],
        }

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
            "volumes": {res.design_surface: vol_json(vol), alt_surface: vol_json(alt)},
        })
    def areas(s):
        return {
            res.design_surface: {"fill_ft2": _round(s.fill_ft2, 2), "cut_ft2": _round(s.cut_ft2, 2)},
            alt_surface: {"fill_ft2": _round(s.alt_fill_ft2, 2), "cut_ft2": _round(s.alt_cut_ft2, 2)},
        }
    sections = [{
        "id": i,
        "page": s.page,
        "station": s.station_label,
        "station_ft": s.station_ft,
        "label_source": s.label_source,
        "areas": areas(s),               # what volumes use: measured, or the user's edit
        "measured": areas(s),            # as traced from the drawing, never changed
        "zero_reason": s.zero_reason,
        "method": s.method,
        "page_kind": s.page_kind,
        "road": road_of.get(i),
        "warnings": s.warnings,
        "overlay": f"/api/jobs/{job.id}/sections/{i}.png" if s.overlay_png else None,
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
        },
        "zero_reasons": ZERO_REASONS,
        "roads": roads,
        "sections": sections,
        "warnings": res.warnings,
        "edits": {res.design_surface: {}, alt_surface: {}},   # section id -> {fill_ft2, cut_ft2}
    }


def _run(job: Job, path: str) -> None:
    def progress(done: int, total: int) -> None:
        job.done, job.total = done, total

    with SLOTS:                       # stays "queued" until a slot is free
        job.status = "running"
        try:
            res = process_plan_set(path, progress=progress)
            job.result = res
            job.payload = serialize(job, res)
            job.pdf_path = path
            job.status = "done"
        except Exception as e:  # surfaced to the client, not swallowed
            job.status, job.error = "error", f"{type(e).__name__}: {e}"
            shutil.rmtree(os.path.dirname(path), ignore_errors=True)


def _job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown or expired job.")
    return job


@app.get("/api/health")
def health():
    deps = {"tesseract": shutil.which("tesseract") is not None}
    return {"ok": all(deps.values()), "version": __version__, "dependencies": deps,
            "max_upload_mb": MAX_UPLOAD_MB}


ACCURACY_FILE = os.environ.get(
    "ACCURACY_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "accuracy.json"))


@app.get("/api/accuracy")
def accuracy():
    """Measured accuracy per plan-set format (written by tools.accuracy_report)."""
    try:
        with open(ACCURACY_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise HTTPException(404, "No accuracy report has been generated.") from None


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...)):
    _expire()
    name = os.path.basename(file.filename or "plan-set.pdf")
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF plan set.")
    tmp = tempfile.mkdtemp(prefix="earthwork_")
    path = os.path.join(tmp, "upload.pdf")
    size = 0
    with open(path, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_MB << 20:
                shutil.rmtree(tmp, ignore_errors=True)
                raise HTTPException(413, f"This PDF is larger than the server's {MAX_UPLOAD_MB} MB upload limit. "
                                         f"Raise it with the MAX_UPLOAD_MB setting on the backend.")
            out.write(chunk)
    with open(path, "rb") as fh:
        if fh.read(5) != b"%PDF-":
            shutil.rmtree(tmp, ignore_errors=True)
            raise HTTPException(400, "That file is not a PDF.")
    job = Job(id=uuid.uuid4().hex[:12], filename=name)
    with LOCK:
        JOBS[job.id] = job
    threading.Thread(target=_run, args=(job, path), daemon=True).start()
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _job(job_id)
    body = {"job_id": job.id, "filename": job.filename, "status": job.status,
            "progress": {"done": job.done, "total": job.total}, "error": job.error}
    if job.status == "done":
        body["result"] = job.payload
    return body


@app.get("/api/jobs/{job_id}/sections/{n}.png")
def section_png(job_id: str, n: int):
    job = _job(job_id)
    if job.result is None or not 0 <= n < len(job.result.sections):
        raise HTTPException(404, "No such section.")
    png = job.result.sections[n].overlay_png
    if not png:
        raise HTTPException(404, "No overlay for this section.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


MAX_AREA_FT2 = 1e6


def _area(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= MAX_AREA_FT2:
        raise HTTPException(400, f"Areas must be numbers between 0 and {MAX_AREA_FT2:g} sq ft.")
    return _round(v, 2)


def _recompute_volumes(payload: dict, surface: str) -> None:
    """Rebuild every road's average-end-area volumes for `surface` from the
    sections' current (possibly edited) areas."""
    @dataclass
    class _Station:
        station_label: str
        station_ft: float
        fill_ft2: float
        cut_ft2: float

    secs = payload["sections"]
    for road in payload["roads"]:
        stations = [_Station(secs[i]["station"], secs[i]["station_ft"], **secs[i]["areas"][surface])
                    for i in road["sections"] if secs[i]["station_ft"] is not None]
        vol = average_end_area_volume(stations, road["label"])
        road["volumes"][surface] = {
            "fill_cy": _round(vol.total_fill_cy),
            "cut_cy": _round(vol.total_cut_cy),
            "net_cy": _round(vol.total_net_cy),
            "segments": [{
                "from": g.station_from, "to": g.station_to, "length_ft": _round(g.length_ft, 2),
                "fill_cy": _round(g.fill_cy), "cut_cy": _round(g.cut_cy), "net_cy": _round(g.net_cy),
                "warning": g.warning,
            } for g in vol.segments],
        }


@app.put("/api/jobs/{job_id}/edits")
def save_edits(job_id: str, body: dict = Body(...)):
    """Save hand-edited areas for one surface, e.g.
    {"surface": "subgrade", "edits": {"12": {"fill_ft2": 40.5, "cut_ft2": 3}, "13": null}}.
    null puts a section back to its measured areas. Road volumes for that
    surface are recomputed; the updated result is returned."""
    job = _job(job_id)
    if job.payload is None:
        raise HTTPException(409, "Job is not finished.")
    surface = _surface(job, body.get("surface"))
    edits = body.get("edits")
    if not isinstance(edits, dict) or len(edits) > len(job.payload["sections"]):
        raise HTTPException(400, "edits must map section ids to {fill_ft2, cut_ft2} or null.")
    parsed: dict[int, dict | None] = {}
    for key, val in edits.items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Unknown section {key!r}.") from None
        if not 0 <= i < len(job.payload["sections"]):
            raise HTTPException(400, f"Unknown section {key!r}.")
        if val is None:
            parsed[i] = None
        elif isinstance(val, dict):
            parsed[i] = {"fill_ft2": _area(val.get("fill_ft2")), "cut_ft2": _area(val.get("cut_ft2"))}
        else:
            raise HTTPException(400, f"Section {key}: expected {{fill_ft2, cut_ft2}} or null.")
    with LOCK:
        saved = job.payload["edits"][surface]
        for i, val in parsed.items():
            sec = job.payload["sections"][i]
            if val is None or val == sec["measured"][surface]:
                saved.pop(str(i), None)
                sec["areas"][surface] = dict(sec["measured"][surface])
            else:
                saved[str(i)] = val
                sec["areas"][surface] = dict(val)
        _recompute_volumes(job.payload, surface)
        return job.payload


def _csv(rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _surface(job: Job, surface: str | None) -> str:
    surfaces = job.payload["summary"]["surfaces"]
    surface = surface or surfaces[0]
    if surface not in surfaces:
        raise HTTPException(400, f"surface must be one of {surfaces}")
    return surface


@app.get("/api/jobs/{job_id}/volumes.csv")
def volumes_csv(job_id: str, exclude: list[str] = Query(default=[]), surface: str | None = None):
    job = _job(job_id)
    if job.payload is None:
        raise HTTPException(409, "Job is not finished.")
    surface = _surface(job, surface)
    n_edited = len(job.payload["edits"][surface])
    title = f"Measured to {surface}" + (f"; {n_edited} section(s) edited by hand" if n_edited else "")
    rows = [[title], ["Road", "From", "To", "Length (ft)", "Fill (cy)", "Cut (cy)", "Net (cy)", "Note"]]
    tf = tc = 0.0
    for r in job.payload["roads"]:
        if r["id"] in exclude:
            continue
        v = r["volumes"][surface]
        for s in v["segments"]:
            rows.append([r["label"], s["from"], s["to"], s["length_ft"], s["fill_cy"], s["cut_cy"], s["net_cy"], s["warning"] or ""])
        rows.append([r["label"], "TOTAL", "", "", v["fill_cy"], v["cut_cy"], v["net_cy"], "; ".join(r["flags"])])
        tf, tc = tf + v["fill_cy"], tc + v["cut_cy"]
    rows.append(["ALL ROADS", "", "", "", _round(tf), _round(tc), _round(tf - tc), ""])
    return _csv(rows, f"{os.path.splitext(job.filename)[0]}-volumes-{surface}.csv")


@app.get("/api/jobs/{job_id}/sections.csv")
def sections_csv(job_id: str):
    job = _job(job_id)
    if job.payload is None:
        raise HTTPException(409, "Job is not finished.")
    roads = {r["id"]: r["label"] for r in job.payload["roads"]}
    a, b = job.payload["summary"]["surfaces"]
    edits = job.payload["edits"]
    rows = [["Page", "Station", "Station source", "Road",
             f"Fill to {a} (sq ft)", f"Cut to {a} (sq ft)", f"Fill to {b} (sq ft)", f"Cut to {b} (sq ft)",
             "Edited by hand", "Method", "Warnings"]]
    for s in job.payload["sections"]:
        edited = [sf for sf in (a, b) if str(s["id"]) in edits[sf]]
        note = "; ".join(f"{sf} (measured fill {s['measured'][sf]['fill_ft2']}, cut {s['measured'][sf]['cut_ft2']})"
                         for sf in edited)
        rows.append([s["page"], s["station"] or "", s["label_source"] or "", roads.get(s["road"], ""),
                     s["areas"][a]["fill_ft2"], s["areas"][a]["cut_ft2"], s["areas"][b]["fill_ft2"], s["areas"][b]["cut_ft2"],
                     note, s["method"], " | ".join(s["warnings"])])
    return _csv(rows, f"{os.path.splitext(job.filename)[0]}-sections.csv")


@app.get("/api/jobs/{job_id}/annotated.pdf")
def annotated(job_id: str, exclude: list[str] = Query(default=[]), surface: str | None = None):
    """The uploaded PDF, every page as it was, with each measured section's
    cut/fill shading and areas (hand edits included) drawn on it, plus
    summary pages at the end."""
    job = _job(job_id)
    if job.payload is None or job.result is None:
        raise HTTPException(409, "Job is not finished.")
    if not job.pdf_path or not os.path.exists(job.pdf_path):
        raise HTTPException(410, "The original PDF is no longer available for this job.")
    surface = _surface(job, surface)
    with LOCK:
        payload = json.loads(json.dumps(job.payload))      # a consistent snapshot of the edits
    pdf = annotated_pdf(job.pdf_path, [s.geometry for s in job.result.sections], payload, surface, set(exclude))
    name = f"{os.path.splitext(job.filename)[0]}-takeoff.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# Production: serve the built frontend from the same origin, so the app's
# relative /api URLs just work. (In development Vite serves it instead.)
FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist"))
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = os.path.normpath(os.path.join(FRONTEND_DIST, path))
        if path and candidate.startswith(os.path.normpath(FRONTEND_DIST)) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

