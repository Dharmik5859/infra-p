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

**At a glance** (6 scanned plan sets -- 19-series, SR 332 in the 23-series layout,
Perry Creek, SR 70, Webb Creek, Florence -- every cross-section compared with the
exact CAD drawing of the same sheet):

| | |
|---|---|
| Sections found with the right station | **97 %** (351 of 361) |
| Total earthwork volume accuracy (cut + fill) | **98.9 %** (fill 99.7 %, cut 95.9 %) |
| Sections within 25 % / within 10 % | **76 %** / 52 % (typical section error 9.5 %) |
| Plan sets processed without failure | **36 of 36** (858 pages, 2,101 sections) |

The app's **Accuracy** page also lists every PDF with what was found in it and,
where a reference exists (the CAD drawing of the same sheets, or an estimator's
hand takeoff), its volume, fill and cut accuracy -- 14 plan sets in all.

Measured with `backend/tools/evaluate.py` against two independent references:

* **Human takeoffs** – many scans in `EARTHWORK/` carry an estimator's
  red/green cut/fill shading on a transparent layer. The pipeline reads only
  the scan underneath; the shading is then measured as the human answer.
* **Exact vector geometry** – for vector PDFs the surfaces are read exactly
  from the CAD strokes; the scan path is scored against them (and the
  19-series scans against the vector sheets they were made from).

Totals are the sum of fill (or cut) area over all checked sections; "within 10 %"
counts sections whose fill + cut is within 10 % of the reference (sections under
10 ft² in total are left out of that share).

| Plan set | Checked against | Sections | Total fill | Total cut | Within 10 % | Typical section error |
|---|---|---|---|---|---|---|
| **19-series** scans | CAD geometry of the same sheets (`highway_planning1.pdf`) | 80 (all stations read correctly) | +1.2 % | −3.9 % | 87 % | 1.5 % |
| **23-series layout** (SR 332 scans) | CAD geometry of the same sheets | 99 | −5.0 % | +7.9 % | 39 % | 14.9 % |
| SR 332 scans | estimator's hand takeoff | 96 | +37.8 % | +12.7 % | 10 % | 28 % |
| 12 EARTHWORK scan sets (538 sections) | estimators' hand takeoffs | 538 | +33.6 % | +8.9 % | 24 % | 26 % |
| Florence Rd scans (resurfacing) | CAD geometry of the same sheets | 23 | +38.2 % | +22.6 % | 23 % | 16 % |
| `highway_planning1.pdf` read as an image | its own CAD geometry | 160 | +0.2 % | −29.9 %¹ | 85 % | 1.4 % |

Every PDF in the dataset (36 plan sets: 19-series, 23-series, CAD exports,
staging sets) was also run end to end: none failed. Sections with no earthwork
(bridge spans, sections outside the construction limits, staging sheets,
resurfacing) are labelled with the reason rather than shown as a bare 0 / 0.

Verdicts shown in the app: **19-series – Excellent**, **23-series – Fair**
(totals within 10 %, but individual sections scatter more).

* CAD-exported PDFs such as `highway_planning1.pdf` are measured from the
  drawing's own linework, so they are exact up to how the sheet is drawn.
* ¹ Five sections near the bridge (30+50 – 32+50) carry a flat "remove below
  elevation 640" line; the CAD reading counts it as cut, the image reading
  treats it as a ruler. Without those stations the cut total is −0.9 %.
* The 23-series sample itself carries no estimator takeoff; SR 332 is the same
  sheet format and has both a CAD twin and a takeoff. Its remaining outliers are
  sheet-specific: an ambiguous ground line at 82+50 (most of the fill gap against
  the estimator), a template the scan does not show at 135+00, and grading
  "by others" counted as cut at 67+50. The two references also disagree with
  each other: estimators measure to their own conventions.

Regenerate with the commands under **Testing**.

---

## The app

A dashboard with a sidebar (Dashboard · New takeoff · Results · Accuracy) and a top bar.

* **Dashboard** – a verdict card for the 19-series and the 23-series: fill and cut accuracy,
  share of sections within 10 %, typical section error, and what it was checked against;
  plus the latest takeoff's cut, fill and net volume.
* **New takeoff** – drop a plan-set PDF; progress is shown page by page.
* **Results** – roads (toggle which count toward the total), the cut/fill profile with
  mass curve, every cross-section with its audit overlay (← / → to step), the volume table,
  sections that need review, CSV export, and a switch between subgrade and finished grade.
* **Editing areas** – any section's fill and cut can be corrected, in the section viewer or
  in the *Edit areas* table. The chart, mass curve, volumes and totals update as you type;
  **Save changes** stores the edits on the server (volumes recomputed by average end area,
  CSV exports and the PDF use them, and the measured values are kept so any edit can be reset).
* **Download PDF** – your original plan set back, page for page, with the cut/fill
  shading, the traced lines and a label (station, fill, cut, edits) on every section,
  and summary pages with the volumes per road.
  Edited sections are marked in the chart and tables. Edits live as long as the job does.
* **Accuracy** – every evaluation in one table, how it was measured, and known limits.

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

### Large plan sets

Scanned plan sets are big (100 MB+ is common). The app uploads them in
**chunks** (8 MB by default, `UPLOAD_CHUNK_MB`), so the request-size limits of
anything in front of it -- nginx (1 MB by default), dev tunnels such as GitHub
Codespaces port forwarding, hosting platforms -- never see the whole file. If a
proxy still refuses a chunk as too large, the browser halves the chunk size and
retries, down to 256 KB; dropped connections are retried too. The backend
reassembles the file and caps the total at `MAX_UPLOAD_MB` (default 2048 MB),
which the upload page shows.

For better throughput behind nginx you can still allow bigger requests:

```nginx
client_max_body_size 64m;
proxy_read_timeout 600s;
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
| `GET` | `/api/accuracy` | measured accuracy per plan-set format (drives the dashboard) |
| `POST` | `/api/jobs` | upload a PDF (`file`) in one request, returns `{job_id}`; jobs run one at a time and queue |
| `POST` | `/api/uploads` | start a chunked upload `{"filename", "size"}` → `{upload_id, chunk_size}` (what the app uses) |
| `PUT` | `/api/uploads/{id}/{n}` | chunk `n` as raw bytes, in order (re-sending the last one is safe) |
| `POST` | `/api/uploads/{id}/complete` | assemble the PDF and start the job → `{job_id}` |
| `GET` | `/api/jobs/{id}` | status, progress, and the result when done |
| `GET` | `/api/jobs/{id}/sections/{n}.png` | audit overlay of one section |
| `GET` | `/api/jobs/{id}/sections/{n}/profile.json` | the section's traced lines in image pixels (the app shades fill/cut from them, following edits) |
| `GET` | `/api/jobs/{id}/volumes.csv?surface=subgrade&exclude=r2` | volumes per road |
| `GET` | `/api/jobs/{id}/sections.csv` | areas per section, both surfaces (notes hand edits) |
| `GET` | `/api/jobs/{id}/annotated.pdf?surface=&exclude=` | the original PDF, every page unchanged, with cut/fill shading and areas (edits included) drawn on each section, plus summary pages |
| `PUT` | `/api/jobs/{id}/edits` | save hand-edited areas `{"surface": "subgrade", "edits": {"12": {"fill_ft2": 40, "cut_ft2": 3}, "13": null}}` (`null` = back to measured); volumes are recomputed and the updated result returned |

Environment: `ALLOWED_ORIGINS` (CORS, comma separated), `MAX_CONCURRENT_JOBS` (default 1), `MAX_UPLOAD_MB`
(default 2048), `UPLOAD_CHUNK_MB` (default 8), `JOB_TTL_SECONDS` (default 6 h), `FRONTEND_DIST`, `ACCURACY_FILE`.

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
python -m tools.evaluate markup  SCAN_WITH_TAKEOFF.pdf [...]          --json evals/markup.json
python -m tools.evaluate vector  VECTOR.pdf                           --json evals/hp_vector.json
python -m tools.evaluate pair    SCAN.pdf VECTOR_OF_SAME_SHEETS.pdf   --json evals/s19_pair.json
python -m tools.accuracy_report  evals/        # rewrites accuracy.json for the dashboard
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
  tools/accuracy_report.py  evaluation results -> accuracy.json (dashboard)
  accuracy.json           latest measured accuracy
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
