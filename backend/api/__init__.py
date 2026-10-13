"""
The HTTP layer over gdot_earthwork, assembled into one application by main.py.

    settings.py            environment settings
    jobs.py                job store, processing queue, expiry, receiving uploads
    payload.py             a job's result as the app reads it; hand edits, volumes
    results.py             the calibration and cross-section JSON of a finished job
    schemas.py             their JSON Schemas (backend/schemas), served and put in OpenAPI
    streaming.py           a multipart upload parsed and written to disk as it arrives
    routes_status.py       /api/health, /api/accuracy
    routes_jobs.py         /api/jobs, /api/uploads, edits
    routes_sheets.py       section overlays and whole sheets
    routes_results.py      /api/jobs/{id}/calibration, /cross-sections
    routes_exports.py      CSV tables and the annotated PDF
    routes_comparisons.py  comparisons with provided results, /api/schemas
    public.py              the public API (v1), mounted at /api/v1
"""
