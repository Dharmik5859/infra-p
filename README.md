# Earthwork Takeoff

Reads road **cross-section plan sets** (PDF) and computes **cut / fill volumes**:
it finds every cross-section on every sheet, reads its station, traces the
existing ground and the proposed template, measures the cut and fill area of
each section, groups the sections into roads, and integrates volumes along
each road with the average-end-area method.

It works on all three kinds of plan set in this project:

| Input | Example | How it is read |
|---|---|---|
| Scanned strips, one section per page | `19series.pdf` | pixels + OCR for stations |
| Scanned sheets, several sections per sheet (incl. sheets plotted sideways) | `23_series_sample.pdf`, the `EARTHWORK/` scans | pixels + OCR for stations |
| CAD-exported vector PDF | `highway_planning1.pdf` | the drawing's own linework + text layer |

Plan, profile, cover and notes sheets are skipped automatically.

---

## How it works

```
PDF page ─► pages.py     scan at native resolution, or vector page rendered + its strokes
         ─► frames.py    find each section's grid frame (lattice detection, split at
                         tick-marked axes), read its station (text layer or OCR)
         ─► surfaces.py  trace existing ground (dashed) and proposed template (solid)
                         – vector: from the CAD strokes; raster: from pixels
                         measure fill / cut between ground and the subgrade
plan set ─► stations.py  decode all station labels jointly (fixes OCR misreads)
         ─► roads.py     group sections into roads by document order
         ─► volume.py    average-end-area volume between consecutive stations
```

Details worth knowing:

* **Resolution independent.** Every section is resampled to a fixed 14.4 px/ft
  before tracing, so the same rules apply to 19-series strips (14.4 px/ft),
  23-series sheets (18 px/ft) and vector renders. Different horizontal and
  vertical scales are undone at the same time.
* **Earthwork is measured to the subgrade** (bottom of the pavement
  structure), the standard convention and the one the estimators' takeoffs in
  `EARTHWORK/` use. The finished-grade (top of pavement) figures are computed
  too; the UI and API let you switch.
* **Bridges and structures** (a design line hanging above the ground at both
  ends) are not counted as fill, and are reported.
* **Buried pipes** drawn past the template (a long run that ends still below
  ground) are not counted as cut, and are reported.
* **Stations on scans** are read by OCR with several renderings voting, then
  decoded across the whole document (Viterbi): a road's stations step evenly,
  so a misread like `914+50` between `91+00` and `92+00` is corrected and a
  missing label is inferred. Inferred stations are flagged for review.
* **Repeated sheet series** (the same stations drawn again, e.g. staging) are
  detected and excluded from the grand total by default.
* Every section gets an **audit overlay** (ground, finished grade, subgrade,
  shaded cut/fill) so a reviewer can check the measurement at a glance.

---

## Accuracy

Measured with `backend/tools/evaluate.py` against two independent references:

* **Human takeoffs** – many scans in `EARTHWORK/` carry an estimator's
  red/green cut/fill shading on a transparent layer. The pipeline reads only
  the scan underneath; the shading is then measured as the human answer.
* **Exact vector geometry** – for vector PDFs the surfaces are read exactly
  from the CAD strokes; the scan path is scored against them (and the
  19-series scans against the vector sheets they were made from).

_Measured error rates are being added; see the latest commit history._

---

## Running it

### Backend (Python 3.11+)

```bash
sudo apt-get install tesseract-ocr          # OCR for station labels on scans
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```

### Frontend (Node 18+)

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api to :8000
```

`npm run build` produces `frontend/dist`; the backend serves it automatically
when present, so in production a single `uvicorn` process serves app + API.

### Docker

```bash
docker build -t earthwork .
docker run -p 8000:8000 earthwork        # http://localhost:8000
```

### Command line

```bash
cd backend
python -m gdot_earthwork.cli plans.pdf --out results/
```

Writes `sections.csv`, `volumes.csv` and one overlay PNG per section.

---

## API

| Method | Path | |
|---|---|---|
| `GET` | `/api/health` | dependency check |
| `POST` | `/api/jobs` | upload a PDF (`file`), returns `{job_id}`; jobs run one at a time and queue |
| `GET` | `/api/jobs/{id}` | status, progress, and the result when done |
| `GET` | `/api/jobs/{id}/sections/{n}.png` | audit overlay of one section |
| `GET` | `/api/jobs/{id}/volumes.csv?surface=subgrade&exclude=r2` | volumes per road |
| `GET` | `/api/jobs/{id}/sections.csv` | areas per section, both surfaces |

Environment: `ALLOWED_ORIGINS` (CORS, comma separated), `MAX_CONCURRENT_JOBS` (default 1), `MAX_UPLOAD_MB`
(default 600), `JOB_TTL_SECONDS` (default 6 h), `FRONTEND_DIST`.

---

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The tests generate synthetic plan sets with exactly known geometry (a vector
PDF and a "scanned" copy of it) and check stations, areas, road grouping,
volumes and the HTTP API end to end.

To re-measure accuracy on real plan sets:

```bash
python -m tools.evaluate markup  SCAN_WITH_TAKEOFF.pdf [...]
python -m tools.evaluate vector  VECTOR.pdf
python -m tools.evaluate pair    SCAN.pdf VECTOR_OF_SAME_SHEETS.pdf
```

---

## Project layout

```
backend/
  main.py                 FastAPI app (jobs, overlays, CSV, serves the built frontend)
  gdot_earthwork/
    pages.py              PDF page -> image (+ text, + vector strokes)
    frames.py             section frames, station labels (text / OCR)
    tracing.py            grid stripping, glyph removal, surface tracing primitives
    surfaces.py           ground / design / subgrade extraction, area measurement
    stations.py           whole-document station decoding
    roads.py              grouping sections into roads
    volume.py             average-end-area volumes
    render.py             audit overlay images
    plan_set.py           orchestration (parallel over pages)
    cli.py                command-line entry point
  tools/evaluate.py       accuracy measurement
  tests/                  synthetic-sheet tests
frontend/                 React + Vite app
```

## Known limitations

* Station labels on scans are read by OCR; unusual fonts can still be misread.
  Misreads that break the station sequence are corrected or inferred and
  flagged under **Needs review**, but a label that is wrong *and* plausible
  cannot be detected.
* Sections are assumed to be drawn with a 10 ft major grid (true for every
  sheet series seen so far); `PipelineConfig.grid_ft` changes it.
* Which lines count as "the proposed template" follows the drawing: temporary
  works, staging slopes or removal lines drawn with the same pen as the
  template can be measured as earthwork. The audit overlay shows exactly what
  was measured.
