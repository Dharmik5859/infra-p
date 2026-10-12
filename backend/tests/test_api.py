"""HTTP API round trip on a synthetic plan set."""
import time

from fastapi.testclient import TestClient

import main

from .synth import embankment, make_pdf


def test_job_lifecycle(tmp_path):
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [[embankment("11+50", 651.3, 5.0), embankment("11+00", 651.7, 4.0)]])
    client = TestClient(main.app)

    assert client.get("/api/health").json()["ok"] is True
    r = client.post("/api/jobs", files={"file": ("plans.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    for _ in range(300):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert body["status"] == "done", body.get("error")

    result = body["result"]
    assert result["summary"]["sections"] == 2
    assert result["summary"]["surfaces"] == ["subgrade", "finished"]
    road = result["roads"][0]
    assert road["station_from"] == "11+00" and road["station_to"] == "11+50"
    assert road["volumes"]["subgrade"]["fill_cy"] > 0
    section = result["sections"][0]
    assert section["areas"]["subgrade"]["fill_ft2"] > 100

    png = client.get(section["overlay"])
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    # the overlay's scale and traced lines let the browser shade fill/cut on it
    assert 0 < section["overlay_px_per_ft"] <= 14.4
    prof = client.get(section["profile"]).json()
    assert len(prof["x"]) == len(prof["ground"]) == len(prof["subgrade"]) > 10
    assert prof["size"][0] > 0 and prof["size"][1] > 0
    # the overlay's scale lets the browser turn a region drawn on it into ft²
    assert 0 < section["overlay_px_per_ft"] <= 14.4
    csv = client.get(f"/api/jobs/{job_id}/volumes.csv?surface=finished")
    assert csv.status_code == 200 and "ALL ROADS" in csv.text
    assert client.get(f"/api/jobs/{job_id}/sections.csv").status_code == 200


def test_rejects_non_pdf():
    client = TestClient(main.app)
    r = client.post("/api/jobs", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    r = client.post("/api/jobs", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 400


def test_accuracy_report(tmp_path, monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "ACCURACY_FILE", str(tmp_path / "missing.json"))
    assert client.get("/api/accuracy").status_code == 404
    report = tmp_path / "accuracy.json"
    report.write_text('{"formats": [{"id": "19"}]}')
    monkeypatch.setattr(main, "ACCURACY_FILE", str(report))
    assert client.get("/api/accuracy").json()["formats"][0]["id"] == "19"


def _finished_job(tmp_path, client):
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [[embankment("11+50", 651.3, 5.0), embankment("11+00", 651.7, 4.0)],
                        [embankment("12+00", 651.0, 6.0)]])
    job_id = client.post("/api/jobs", files={"file": ("plans.pdf", pdf.read_bytes(), "application/pdf")}).json()["job_id"]
    for _ in range(300):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert body["status"] == "done", body.get("error")
    return job_id, body["result"]


def test_edits_recompute_volumes_and_revert(tmp_path):
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)
    surface = result["summary"]["design_surface"]
    road = result["roads"][0]
    first, second = road["sections"][0], road["sections"][1]
    before = road["volumes"][surface]

    # recomputing with no edits reproduces the pipeline's own volumes
    main._recompute_volumes(main.JOBS[job_id].payload, surface)
    assert main.JOBS[job_id].payload["roads"][0]["volumes"][surface] == before

    r = client.put(f"/api/jobs/{job_id}/edits",
                   json={"surface": surface, "edits": {str(first): {"fill_ft2": 100, "cut_ft2": 20}}})
    assert r.status_code == 200
    after = r.json()
    sec = after["sections"][first]
    assert sec["areas"][surface] == {"fill_ft2": 100.0, "cut_ft2": 20.0}
    assert sec["measured"][surface] == result["sections"][first]["areas"][surface]
    assert after["edits"][surface] == {str(first): {"fill_ft2": 100.0, "cut_ft2": 20.0}}
    seg = after["roads"][0]["volumes"][surface]["segments"][0]
    b = result["sections"][second]["areas"][surface]
    length = seg["length_ft"]
    assert seg["fill_cy"] == round((100 + b["fill_ft2"]) / 2 * length / 27, 1)
    assert seg["cut_cy"] == round((20 + b["cut_ft2"]) / 2 * length / 27, 1)
    # the other surface is untouched, and the job read back carries the edit
    other = [s for s in result["summary"]["surfaces"] if s != surface][0]
    assert after["roads"][0]["volumes"][other] == road["volumes"][other]
    assert client.get(f"/api/jobs/{job_id}").json()["result"]["edits"][surface]
    # CSV exports use the edited numbers and say so
    assert "edited by hand" in client.get(f"/api/jobs/{job_id}/volumes.csv").text
    assert "measured fill" in client.get(f"/api/jobs/{job_id}/sections.csv").text

    r = client.put(f"/api/jobs/{job_id}/edits", json={"surface": surface, "edits": {str(first): None}})
    assert r.json()["edits"][surface] == {}
    assert r.json()["roads"][0]["volumes"][surface] == before


def test_edits_reject_bad_input(tmp_path):
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)
    surface = result["summary"]["design_surface"]
    url = f"/api/jobs/{job_id}/edits"
    bad = [
        {"surface": "nope", "edits": {}},
        {"surface": surface, "edits": {"999": {"fill_ft2": 1, "cut_ft2": 1}}},
        {"surface": surface, "edits": {"0": {"fill_ft2": -1, "cut_ft2": 1}}},
        {"surface": surface, "edits": {"0": {"fill_ft2": "1", "cut_ft2": 1}}},
        {"surface": surface, "edits": {"0": {"fill_ft2": 1}}},
        {"surface": surface, "edits": ["0"]},
    ]
    for body in bad:
        assert client.put(url, json=body).status_code == 400, body
    assert client.put("/api/jobs/nope/edits", json={"surface": surface, "edits": {}}).status_code == 404


def test_annotated_pdf_keeps_original_pages_and_shows_edits(tmp_path):
    import pymupdf as fitz
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)
    surface = result["summary"]["design_surface"]
    first = result["roads"][0]["sections"][0]
    client.put(f"/api/jobs/{job_id}/edits",
               json={"surface": surface, "edits": {str(first): {"fill_ft2": 432.1, "cut_ft2": 0}}})
    r = client.get(f"/api/jobs/{job_id}/annotated.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    out = fitz.open(stream=r.content, filetype="pdf")
    src = fitz.open(main.JOBS[job_id].pdf_path)
    assert len(out) == len(src) + 1                                # every page kept + a summary page
    assert all(out[i].rect == src[i].rect for i in range(len(src)))
    text = "".join(p.get_text() for p in out)
    assert "STA 11+00" in text and "STA 12+00" in text             # every section labelled
    assert "432.1" in text and "EDITED" in text                    # the edit is on the sheet
    assert "Earthwork takeoff" in out[-1].get_text()


def test_upload_limit_is_reported_and_enforced(tmp_path, monkeypatch):
    client = TestClient(main.app)
    assert client.get("/api/health").json()["max_upload_mb"] == main.MAX_UPLOAD_MB
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"0" * (2 << 20))           # a 2 MB "plan set"
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", 1)
    r = client.post("/api/jobs", files={"file": ("big.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 413
    assert "MAX_UPLOAD_MB" in r.json()["detail"]


def test_chunked_upload_assembles_the_pdf_and_runs_the_job(tmp_path):
    client = TestClient(main.app)
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [[embankment("11+50", 651.3, 5.0), embankment("11+00", 651.7, 4.0)]])
    data = pdf.read_bytes()
    r = client.post("/api/uploads", json={"filename": "plans.pdf", "size": len(data)})
    assert r.status_code == 200
    uid = r.json()["upload_id"]
    parts = [data[i:i + 4096] for i in range(0, len(data), 4096)]
    for i, part in enumerate(parts):
        assert client.put(f"/api/uploads/{uid}/{i}", content=part).status_code == 200
    # a retried chunk (response lost) is acknowledged, not written twice
    assert client.put(f"/api/uploads/{uid}/{len(parts) - 1}", content=parts[-1]).json()["received"] == len(data)
    job_id = client.post(f"/api/uploads/{uid}/complete").json()["job_id"]
    for _ in range(300):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert body["status"] == "done", body.get("error")
    assert body["result"]["summary"]["sections"] == 2
    with open(main.JOBS[job_id].pdf_path, "rb") as fh:
        assert fh.read() == data


def test_chunked_upload_rejects_bad_sequences(tmp_path, monkeypatch):
    client = TestClient(main.app)
    uid = client.post("/api/uploads", json={"filename": "a.pdf", "size": 10}).json()["upload_id"]
    assert client.put(f"/api/uploads/{uid}/1", content=b"12345").status_code == 409      # out of order
    assert client.put(f"/api/uploads/{uid}/0", content=b"%PDF-").status_code == 200
    assert client.post(f"/api/uploads/{uid}/complete").status_code == 400               # incomplete
    assert client.put(f"/api/uploads/{uid}/1", content=b"123456").status_code == 413     # past declared size
    assert client.put("/api/uploads/nope/0", content=b"x").status_code == 404
    assert client.post("/api/uploads", json={"filename": "a.txt", "size": 10}).status_code == 400
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", 1)
    assert client.post("/api/uploads", json={"filename": "a.pdf", "size": 2 << 20}).status_code == 413


def test_marked_areas_are_measured_kept_and_drawn(tmp_path):
    import pymupdf as fitz
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)
    surface = result["summary"]["design_surface"]
    sec = result["sections"][result["roads"][0]["sections"][0]]
    ppf = sec["overlay_px_per_ft"]
    # a 10 ft x 4 ft rectangle outlined on the image, marked as cut
    box = [[100, 100], [100 + 10 * ppf, 100], [100 + 10 * ppf, 100 + 4 * ppf], [100, 100 + 4 * ppf]]
    m = sec["measured"][surface]
    edit = {"fill_ft2": m["fill_ft2"], "cut_ft2": round(m["cut_ft2"] + 40, 2), "marks": [{"kind": "cut", "pts": box}]}
    r = client.put(f"/api/jobs/{job_id}/edits", json={"surface": surface, "edits": {str(sec["id"]): edit}})
    assert r.status_code == 200
    saved = r.json()["sections"][sec["id"]]
    assert saved["marks"][surface][0]["kind"] == "cut"
    assert abs(saved["marks"][surface][0]["ft2"] - 40) < 0.5
    assert saved["areas"][surface]["cut_ft2"] == edit["cut_ft2"]
    assert str(sec["id"]) in r.json()["edits"][surface]

    before = fitz.open(main.JOBS[job_id].pdf_path)[sec["page"] - 1].get_drawings()
    out = fitz.open(stream=client.get(f"/api/jobs/{job_id}/annotated.pdf").content, filetype="pdf")
    assert len(out[sec["page"] - 1].get_drawings()) > len(before)

    # bad marks are refused; null clears the edit and its marks
    for marks in ([{"kind": "x", "pts": box}], [{"kind": "fill", "pts": box[:2]}], [{"kind": "fill", "pts": [["a", 1]] * 3}]):
        bad = {str(sec["id"]): {**edit, "marks": marks}}
        assert client.put(f"/api/jobs/{job_id}/edits", json={"surface": surface, "edits": bad}).status_code == 400
    r = client.put(f"/api/jobs/{job_id}/edits", json={"surface": surface, "edits": {str(sec["id"]): None}})
    assert r.json()["sections"][sec["id"]]["marks"][surface] == []
