# Earthwork Takeoff

Upload a road plan set (PDF) and get the cut and fill of every cross-section,
the volumes per road, and the feet-to-pixel calibration of every sheet.

## What to upload

* **One PDF** with the cross-section sheets: CAD exports or scans both work.
  The whole plan set is fine; pages without cross-sections are skipped.
* Staged sets: keep the stage in the file name or title block (e.g.
  `ROAD - STAGE 2.pdf`); only that stage's work is measured.
* Large files (100 MB+) are fine: the app uploads in chunks (limit
  `MAX_UPLOAD_MB`, default 2048).

## Run it

Backend (Python 3.11+):

```bash
sudo apt-get install tesseract-ocr     # OCR for scanned sheets
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```

Frontend (Node 18+), in a second terminal:

```bash
cd frontend
npm install
npm run dev                            # open http://localhost:5173
```

Or with Docker: `docker build -t earthwork . && docker run -p 8000:8000 earthwork`,
then open http://localhost:8000.

## Use it

* **New takeoff**: upload the PDF. **Results** then shows every section (traced
  lines over the drawing), cut / fill per side and the volumes. Sections below
  85 % confidence are flagged for review and can be edited.
* **Calibration**: upload the PDF to get each sheet's scale as JSON.
* **API**: try the two API endpoints in the browser and copy the code to call them.

## API

| Endpoint | Returns |
|---|---|
| `POST /api/v1/calibration` (form field `file` = the PDF) | job id (`202`), or the result when ready within `?wait=` seconds |
| `GET /api/v1/calibration/{id}` | feet-to-pixel calibration of every sheet |
| `POST /api/v1/cross-sections` (form field `file`) | job id (`202`), or the result when ready within `?wait=` seconds |
| `GET /api/v1/cross-sections/{id}` | every cross-section: station, left / right cut and fill, confidence |

`202` means still processing: poll the `GET` until it returns `200`. Full docs
at `/api/v1/docs`. Set `API_KEYS=key1,key2` on the server to require an
`X-API-Key` header.

```bash
curl -F "file=@plans.pdf" "http://localhost:8000/api/v1/cross-sections?wait=300"
```

## Tests

```bash
cd backend && python -m pytest -q
```
