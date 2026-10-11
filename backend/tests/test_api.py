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
