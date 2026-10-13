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

The pipeline runs as six independent stages (`gdot_earthwork/stages/`), each
with plain inputs and outputs so it can be run, tested or replaced on its own:

```
PDF page ─► 1 ingest     stages/ingest.py     scan at native resolution, or vector page rendered + its strokes
         ─► 2 detect     stages/detect.py     each section's grid frame (lattice detection, split at
                                              tick-marked axes) and its station (text layer or OCR)
         ─► 3 calibrate  stages/calibrate.py  ft per grid square ACROSS and UP, read off the section's
                                              offset and elevation labels; its centreline (offset 0)
         ─► 4 trace      stages/trace.py      existing ground (dashed) and proposed template (solid)
                                              – vector: from the CAD strokes; raster: from pixels
         ─► 5 measure    stages/measure.py    fill / cut to subgrade and finished grade, per 1 ft strip
                                              (left / right of the centreline), warnings
plan set ─► 6 decode     stages/decode.py     all station labels decoded jointly (fixes OCR misreads)
         ─► roads.py       group sections into roads by document order
         ─► confidence.py  a 0-100 score per section; below 85 it carries alerts
         ─► volume.py      average-end-area volume between consecutive stations
```

Details worth knowing:

* **Resolution independent.** Every section is resampled to a fixed 14.4 px/ft
  before tracing, so the same rules apply to 19-series strips (14.4 px/ft),
  23-series sheets (18 px/ft) and vector renders. Different horizontal and
  vertical scales are undone at the same time.
* **Scale per axis, from the drawing.** The calibrate stage reads how many feet
  one grid square is on each axis: across from the offset labels under the
  section (the PDF text on CAD sheets; on scans from where the labels turn from
  two digits to three, and only with OCR of the widest labels agreeing when
  that points away from 10 ft), up from the elevation labels beside it (text,
  or OCR on scans). Only steps drawings use (1, 2, 2.5, 4, 5, 10, 20, 25, 40, 50, 100 ft)
  and only when three or more labels agree; otherwise 10 ft, flagged as
  assumed. Tested on sheets drawn at 10 × 10, 10 × 5 (2× vertical), 20 × 20 and
  20 × 5 ft, as vector and as scan (`tests/test_calibrate.py`); every real
  sheet checked (19-series, 23-series, SR 70, SR 332, SR 136, Perry Creek,
  Hamilton, Franklin Gateway, SR 5) reads 10 × 10 ft, as drawn
  (`python -m tools.calibration_check`).
* **Confidence per section.** Each section is scored 0-100 from what had to be
  guessed: how its station was read (text, OCR agreement, inferred), whether
  its scale and centreline were read or assumed, scan vs CAD, surfaces
  bridged over gaps, runs left out, a 0 / 0 result with no design line, and an
  area far off both neighbours'. Every deduction is listed. 85 and above
  passes; below 85 the section gets an alert (in the API and in the app).
* **Earthwork is measured to the subgrade** (bottom of the pavement
  structure), the standard convention and the one the estimators' takeoffs in
  `EARTHWORK/` use. The finished-grade (top of pavement) figures are computed
  too; the UI and API let you switch.
* **Bridges and structures** (a design line hanging above the ground at both
  ends) are not counted as fill, and are reported.
* **Buried pipes** drawn past the template (a long run that ends still below
  ground) are not counted as cut, and are reported. A run deeper than 15 ft
  passing under the middle of the section is the template itself (a deep
  cut the frame cuts off before it climbs out) and is kept.
* **Checked against the estimators' labels** after these changes: all 16
  labelled plan sets give the same areas as before, section for section,
  except Mountain Industrial Blvd 309+00 – 310+00, which moved closer to the
  labels.
* **Cut and fill.** Where the proposed surface (subgrade) lies below the
  existing line the earth between them is cut; where it lies above, the space
  between them is fill. The existing line is the top of what is there:
  existing asphalt in a cut is dug out with the earth and counted as cut;
  under a fill it stays and the fill is built on it, so it is never counted;
  poles (thin uprights) change nothing (`tests/test_existing_features.py`).
* **Ground far below the template.** Under a tall embankment (or in a deep
  cut) the existing ground is often a faint, broken dashed line. Where the
  ground trace rides along the template for more than 15 ft while ground
  dashes exist elsewhere in those columns, the ground is not hidden there:
  those columns are re-traced on the dashes alone.
* **Staged-construction sheets** (the file names a stage): only the sheet's
  own stage is measured. The sheet's stage is read from its title block
  ("STAGE 3", "STAGE 1B"); stretches marked "STAGE 2 CONSTRUCTION" for
  another stage (found with their dimension line) are traced and measured
  without, and the section says so. A mark for the sheet's own stage changes
  nothing (`tests/test_staging.py`).
* **Title blocks.** A stroke lying wholly in the strip below a section's axis
  and made of horizontal / vertical rules (a scale bar, a table) is not part
  of the section.
* **Walls.** Where the template ends at a wall's foot deep below ground, the
  back slope drawn above the wall is followed up to the ground and measured
  (`tests/test_walls.py`).
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

Measured **only against labelled data**: the cut (red) and fill (green) that
estimators shaded by hand on scanned plan sets in `EARTHWORK/`. The pipeline reads
the scan underneath without seeing the shading; every section the estimator shaded
is compared (`backend/tools/labelled_eval.py`, 16 labelled PDFs, 769 sections).

| Against the estimators' labels | Mainline sheets (10 sets, 478 sections) | All labelled sheets (16 sets, 769 sections) |
|---|---|---|
| Cut + fill total | **98.0 %** (+2.0 %) | 91.3 % (+8.7 %) |
| Fill / cut | +7.3 % / −2.7 % | +19.1 % / −1.4 % |
| Sections within 25 % / 10 % | **63 %** / 36 % (typical difference 17.4 %) | 54 % / 31 % (typical 21.4 %) |
| Estimators' shading inside a section the pipeline found | 97.6 % | 98.0 % |

Staged-construction sheets are the gap between the two columns: they show the same
cross-sections as the mainline set, but the estimator shades only that stage's work.
The pipeline now reads the sheet's stage from the title block and leaves out stretches
marked "STAGE n CONSTRUCTION" for another stage (`gdot_earthwork/staging.py`).
The 19-series has no labelled copy in the data, so it is not scored; the 23-series
sample's labelled copy (Mountain Ind Blvd mainline) comes out at 89.3 % (fill +0.6 %,
cut −19.4 %). The app's **Accuracy** page shows every labelled plan set.

The label area is measured shape by shape: the bright fill plus half of each shape's
outline (drawn on the shape's edge); orange and brown notes are not counted. On shapes
of known size in the estimators' colours this is within 1 % (a few % on 1 ft slivers).

### Plan-set audit (unlabelled Drive sets)

Plan sets with no estimator shading (Franklin Gateway, CALL 011 / 022 / 024 / 025,
New Hope at Wylie, SR 5 Connector) were audited section by section:
`backend/tools/audit_plan_set.py PLANS.pdf OUT_DIR --raster-check` writes every
section's overlay next to the same crop of the original sheet, the calibration and
cross-section JSON, and (for CAD sheets) a second, independent reading from pixels.
Each overlay was compared with the drawing and the areas estimated from the grid.

* **Calibration** was right on every set. Franklin and CALL 025 are printed at half
  size (their notes say 1" = 10', the grid measures 1" = 20'); this is now detected
  and reported (`printScale`, `noteCheck.printRatio`), and the grid wins.
* **SR 5 Connector mainline** against the delivered takeoff (xlsx): cut −1.2 %,
  fill −1.2 %, left / right within 4.5 %.
* Round 1 (Franklin, CALL 011, CALL 025): 56 of 61 sections correct. Round 2 (all
  sets): 163 of 232. The failure modes found and fixed since:
  - textless CAD sheets (New Hope: lettering drawn as strokes) found 0 sections → 27:
    labels read by OCR, ground drawn dash by dash, underlines of notes ignored;
  - template carried on across small breaks in the linework;
  - title-block borders and scale bars hanging into the grid margins ignored;
  - leaders to notes ("EDGE OF STREAM BANK") and bold labels no longer traced as
    template (CALL 022 200+00 fill 132 → 7 ft², 600+93 false cut 212 → 0);
  - widenings drawn apart from the rest of the template are traced (CALL 024
    136+00 … 140+00 right-side cut now within ~10 % of the audit estimates);
  - sections at a bridge are flagged for review.

---

## The app

A dashboard with a sidebar (Dashboard · New takeoff · Results · Calibration · Comparison · Accuracy) and a top bar.

* **Dashboard** – a verdict card for the 19-series and the 23-series, scored against the
  estimators' labels where a labelled copy exists (fill and cut accuracy, share of sections
  within 10 %, typical section difference);
  plus the latest takeoff's cut, fill and net volume.
* **New takeoff** – drop a plan-set PDF; progress is shown page by page.
* **Results** – roads (toggle which count toward the total), the cut/fill profile with
  mass curve, every cross-section with its audit overlay (← / → to step), the volume table,
  sections that need review, CSV export, and a switch between subgrade and finished grade.
* **Calibration** – upload a whole plan set and press **Analyze**: the feet-to-pixel scale of
  every sheet comes back as JSON (shown in a scrollable viewer with copy / download, and how
  to call it from cURL, Python or JavaScript underneath). Each sheet's scale is measured from
  its cross-section grid, or read from a scale note printed on it (1" = 20', HORIZ / VERT),
  or from the document's scale note (often on the first page); pixels are PDF points as
  displayed, i.e. a PDF viewer at 100 %. Every calibration follows the app's format
  (`pixelLengthX/Y` = `realWorldLengthX/Y` ft, `scaleX/Y` ft per pixel), and the response
  also lists every cut / fill area as a shape (`points` offsets from `position2D`, `side`,
  `stationId`, `stage`, `streetName`, `areaSqFt`). Each calibration also gives
  `pixelsPerFootX/Y` and the grid's feet per square on each axis (`gridScale`, as read
  off the axis labels). On SR 70 the measured grid gives 36.00 px per 10 ft, exactly its
  printed 1" = 20'. The same viewer shows the **cross-section JSON** (every section's
  left / right / total cut and fill, its shapes, confidence and alerts), the **alerts**
  alone, and the **JSON Schema** the responses are validated against.
* **Confidence and alerts** – every section shows its score (a ring badge: green passes,
  amber / red below 85 %) in the viewer header and the *All values* table; below 85 % the
  viewer lists what lowered it, and the section appears under **Needs review**, lowest
  score first.
* **Comparison** – our takeoff against results provided for the same plan set. The SR 5
  connector comparison ships with the app (station by station, left / right cut and fill,
  volumes per street and stage, what causes the differences); any open takeoff can be
  compared with a results spreadsheet in the same format.
* **Sheet view** – the results open on the whole sheet of the original PDF with every
  measured cross-section outlined, its cut / fill shaded and its station, fill and cut
  labelled. Click a section to select it (zoom with the wheel, drag to move, *Whole sheet* /
  *This section*). **All values** opens a table of every section's fill, cut, net and left /
  right split (sortable, searchable, with totals); picking a row, a chart bar or ← / → moves
  the view to that sheet and zooms onto the section. *Section* shows one section close up.
* **Left / right of the centreline** – every section's fill and cut are also split at the
  centreline (offset 0): left fill, left cut, right fill, right cut, in the section viewer,
  the edit dialog, the *Edit areas* table, the sections CSV and on the annotated PDF. The
  centreline is read from the section's own offset-axis labels (the PDF text on CAD sheets;
  on scans from the labels' widths -- "0" is one digit, 10-90 two, 100+ three -- with OCR as
  a fallback), drawn on the picture as **CL**. Checked on the 19-series against its CAD
  drawing: the centreline matched on all 75 sections read, and the side totals agree within
  1-3 % (left cut, a small total, 9 %). Where an axis cannot be read the neighbouring
  section's centreline is used and the section is flagged. Edits keep their side: an
  outlined area is split at the centreline, a removed area comes off the side it lies on.
  Volumes are split the same way: each road's left and right fill and cut in cubic yards
  (average end area on each side), shown under the road profile next to the summed section
  areas in ft², in the cut / fill totals, the road list, the Volumes table, the volumes CSV
  and the PDF summary.
* **Editing areas** – **Edit** on any section opens it large: type the fill and cut, or
  click points around an area on the drawing (finish by clicking the first point again,
  double-clicking or pressing Enter) and press **Fill** or **Cut** to add it, or
  **Remove fill** / **Remove cut** to take away shading the pipeline put there by mistake
  (that part goes back to the plain drawing). **Reset** goes back to the measurement. The green / red shading on the picture follows every change,
  and **Save** stores it. Areas can also be typed in the *Edit areas* table. The chart, mass
  curve, volumes and totals update as you type; saved edits are kept on the server (volumes
  recomputed by average end area, CSV exports and the PDF use them, outlined areas are drawn
  on the PDF, and the measured values are kept so any edit can be reset).
* **Download PDF** – your original plan set back, page for page, with the cut/fill
  shading, the traced lines and a label (station, fill, cut, edits) on every section,
  and summary pages with the volumes per road.
  Edited sections are marked in the chart and tables. Edits live as long as the job does.
* **Accuracy** – results against the estimators' labels only: mainline vs staged sheets,
  every labelled plan set, how it was measured, and what the differences mean.

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

## Public API (v1)

The two deliverables, the **calibration** and the **cross-sections** of a plan set, are
also a documented API for clients outside the app: Swagger UI at **`/api/v1/docs`**,
OpenAPI at `/api/v1/openapi.json` (each `200` response described by its JSON Schema from
`backend/schemas/`). The app's **API** page (`#/api`) is a console for both: upload a
PDF or give a job id, watch it go from `202` to `200`, browse the JSON, and copy
ready-made curl / Python / JavaScript calls.

| Method | Path | |
|---|---|---|
| `POST` | `/api/v1/calibration?wait=` | upload a plan-set PDF (multipart field `file`) → `202` + job status, or `200` + the calibration if it is ready within `wait` seconds (0-600, default 0) |
| `GET` | `/api/v1/calibration/{id}` | `200` the calibration once processed; `202` + progress until then |
| `POST` | `/api/v1/cross-sections?wait=` | the same upload, answered with the cross-sections |
| `GET` | `/api/v1/cross-sections/{id}?surface=` | `200` every cross-section, measured to `subgrade` (default) or `finished`; `202` until ready |
| `GET` | `/api/v1/schemas/{name}` | the JSON Schema (`calibration`, `cross-sections`) of each response |

One processing run serves both: an id from either POST reads either GET, and a plan set
uploaded in the app can be read by its job id (hand edits included). While processing,
the answer is `202` with `{"id", "status": "queued" | "running", "progress": {"done", "total"},
"links": {"self", "calibration", "crossSections"}}` and `Location` / `Retry-After` headers;
every answer names its job in `X-Job-Id` (the only place a POST answered `200` can).

| Status | Meaning |
|---|---|
| `200` | the result (calibration or cross-section JSON) |
| `202` | still queued or running: poll `links.self` |
| `400` | not a PDF, an empty file, a malformed form, or a bad parameter (`wait`, `surface`) |
| `401` | missing or wrong `X-API-Key` (only when `API_KEYS` is set) |
| `404` | unknown or expired id |
| `410` | the uploaded PDF is no longer on the server |
| `413` | the PDF is larger than `MAX_UPLOAD_MB` |
| `422` | the plan set could not be processed; `{"detail": "..."}` says why |

**Authentication.** Start the server with `API_KEYS=key1,key2` and every `/api/v1`
request must send one of them in the `X-API-Key` header (compared in constant time);
without `API_KEYS` the API is open. The docs pages stay readable either way (use
**Authorize** there to try the API), and the app's own `/api/...` endpoints never need a key.

**Large plan sets.** The upload is parsed as it arrives and written straight to disk, a
chunk at a time; it is refused with `413` as soon as it passes `MAX_UPLOAD_MB` (before a
byte is read when its declared length already does). Jobs share the app's queue
(`MAX_CONCURRENT_JOBS`) and expire after `JOB_TTL_SECONDS`.

```bash
# upload and wait (up to 5 minutes) for the result
curl -X POST "http://localhost:8000/api/v1/cross-sections?wait=300" \
     -H "X-API-Key: $API_KEY" -F "file=@plans.pdf" -o cross-sections.json

# or upload, then poll
curl -X POST http://localhost:8000/api/v1/calibration -H "X-API-Key: $API_KEY" -F "file=@plans.pdf"
#   202 {"id": "3f9c2a1b7e4d", "status": "queued", "progress": {"done": 0, "total": 0}, "links": {...}}
curl http://localhost:8000/api/v1/calibration/3f9c2a1b7e4d -H "X-API-Key: $API_KEY"
curl "http://localhost:8000/api/v1/cross-sections/3f9c2a1b7e4d?surface=finished" -H "X-API-Key: $API_KEY"
```

```python
import time
import requests

API = "http://localhost:8000/api/v1"
HEADERS = {"X-API-Key": "..."}                  # only when the server sets API_KEYS

with open("plans.pdf", "rb") as f:
    r = requests.post(f"{API}/calibration", params={"wait": 60}, headers=HEADERS, files={"file": f})
r.raise_for_status()                             # 400 / 401 / 413; 422: r.json()["detail"] says why it failed
job_id = r.headers["X-Job-Id"]
while r.status_code == 202:                      # still processing
    time.sleep(int(r.headers.get("Retry-After", 2)))
    r = requests.get(f"{API}/calibration/{job_id}", headers=HEADERS)
    r.raise_for_status()
calibration = r.json()
cross_sections = requests.get(f"{API}/cross-sections/{job_id}", headers=HEADERS).json()   # same job
```

## API

The app's own endpoints (no API key, not versioned):

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
| `GET` | `/api/jobs/{id}/calibration` | feet-to-pixel calibration of every sheet (grid, sheet note or document note) and the cut / fill areas as page-space shapes |
| `GET` | `/api/jobs/{id}/cross-sections?surface=` | every section in the received cross-section format: station, street, stage, left / right / total cut and fill (sq ft, edits applied), its shapes, `confidence` and `alerts` (below 85 %) |
| `POST` | `/api/jobs/{id}/compare` | compare with provided results (`file`: xlsx / csv, Street · Stage · Station · Delta · Left / Right cut and fill areas and volumes) |
| `GET` | `/api/comparisons`, `/api/comparisons/{name}` | stored comparisons with provided results (`sr5`) |
| `GET` | `/api/schemas/{name}` | the JSON Schemas (`calibration`, `cross-sections`) the responses are validated against |
| `GET` | `/api/jobs/{id}/pages/{n}.png` | a whole sheet of the original PDF, as an image |
| `GET` | `/api/jobs/{id}/pages/{n}.json` | the measured sections on that sheet (frame, traced lines) in its coordinates |
| `GET` | `/api/jobs/{id}/sections.csv` | areas per section, both surfaces, with left / right fill and cut and how the centreline was found (notes hand edits) |
| `GET` | `/api/jobs/{id}/annotated.pdf?surface=&exclude=` | the original PDF, every page unchanged, with cut/fill shading and areas (edits included) drawn on each section, plus summary pages |
| `PUT` | `/api/jobs/{id}/edits` | save hand-edited areas `{"surface": "subgrade", "edits": {"12": {"fill_ft2": 40, "cut_ft2": 3}, "13": null}}` (`null` = back to measured; an edit may carry `"marks": [{"kind": "fill", "pts": [[x, y], …]}]`, areas outlined on the section image); volumes are recomputed and the updated result returned |

Environment: `ALLOWED_ORIGINS` (CORS, comma separated), `MAX_CONCURRENT_JOBS` (default 1), `MAX_UPLOAD_MB`
(default 2048), `UPLOAD_CHUNK_MB` (default 8), `JOB_TTL_SECONDS` (default 6 h), `API_KEYS` (public API keys,
comma separated; unset = open), `FRONTEND_DIST`, `ACCURACY_FILE`.

---

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The tests generate synthetic plan sets with exactly known geometry (a vector
PDF and a "scanned" copy of it) and check stations, areas, road grouping,
volumes and the HTTP API end to end; the scale read on each axis at four grid
scales; walls; the comparison with provided results; every calibration
and cross-section response against the JSON Schemas in `backend/schemas/`; and the
public API (`tests/test_public_api.py`: upload / poll / wait, one id on both endpoints,
errors, API keys, the streamed upload, the OpenAPI document).

```bash
python -m tools.calibration_check out.json PLANS.pdf ...        # scale read per section, per axis
python -m tools.compare_reference PLANS.pdf RESULTS.xlsx comparisons/NAME.json --title "..."
```

To re-measure accuracy on real plan sets:

```bash
python -m tools.labelled_eval   labelled/ EARTHWORK/*/*.pdf   # pipeline vs the estimators' labels, per PDF
python -m tools.accuracy_report labelled/                     # rewrites accuracy.json for the app
```

---

## Project layout

```
backend/
  main.py                 entry point: assembles the app's routers, mounts the public API at
                          /api/v1, serves the built frontend
  api/                    the HTTP layer
    settings.py           environment settings
    jobs.py               job store, processing queue, expiry, uploads (shared by both APIs)
    payload.py            a job's result as the app reads it; hand edits, volume recompute
    results.py            the calibration and cross-section JSON of a finished job
    schemas.py, streaming.py   JSON Schemas for serving / OpenAPI; multipart upload streamed to disk
    routes_*.py           the app's endpoints: jobs & uploads, sheets & images, calibration &
                          cross-sections, exports (CSV / PDF), comparisons & schemas, health & accuracy
    public.py             the public API (v1): its own FastAPI app, OpenAPI and Swagger UI
  schemas/                JSON Schemas of the calibration and cross-section responses
  comparisons/            stored comparisons with provided results (SR 5) + notes
  gdot_earthwork/
    stages/               the pipeline's six stages (ingest, detect, calibrate, trace,
                          measure, decode stations) -- entry points over the modules below
    calibration.py        feet-to-pixel calibration per sheet + cut / fill shapes
    cross_sections.py     the cross-section response
    confidence.py         0-100 score per section, alerts below 85
    compare.py            comparison with provided results
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
  tools/evaluate.py       label measurement and other accuracy checks
  tools/labelled_eval.py  pipeline vs the estimators' labels, per PDF
  tools/accuracy_report.py  labelled results -> accuracy.json (dashboard)
  accuracy.json           latest measured accuracy
  tests/                  synthetic-sheet tests
frontend/                 React + Vite app
```

## Known limitations

* Station labels on scans are read by OCR; unusual fonts can still be misread.
  Misreads that break the station sequence are corrected or inferred and
  flagged under **Needs review**, but a label that is wrong *and* plausible
  cannot be detected.
* Where a section's axis labels cannot be read, its grid is taken as 10 ft a
  square (`PipelineConfig.grid_ft`) and the section says so (scale "assumed").
* Where the existing ground under an embankment is very broken, the trace
  bridges its dips in straight lines (SR 5 314+00: -13 % fill).
* A section at a bridge (BEGIN / END BRIDGE marked) is measured as drawn and
  flagged for review: the space under the deck reads as fill.
* On textless CAD sheets stations come from OCR of stroke lettering; a few
  read wrong and are flagged (New Hope).
* Which lines count as "the proposed template" follows the drawing: temporary
  works, staging slopes or removal lines drawn with the same pen as the
  template can be measured as earthwork. The audit overlay shows exactly what
  was measured.
