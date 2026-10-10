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
