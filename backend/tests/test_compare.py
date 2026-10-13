"""Comparing a takeoff with provided results: the spreadsheet format as
received (areas in yd², a subtotal per street / stage), matched by station."""
import csv
import io

from fastapi.testclient import TestClient

import main
from gdot_earthwork.compare import read_reference

from .test_api import _finished_job

HEAD = [["Street", "Stage", "Station Number", "Delta", "Left", "", "", "", "Right", "", "", "", "Total Volume", ""],
        ["", "", "", "", "Cut Area (yd²)", "Fill Area (yd²)", "Cut Vol (CY)", "Fill Vol (CY)",
         "Cut Area (yd²)", "Fill Area (yd²)", "Cut Vol (CY)", "Fill Vol (CY)", "Cut (CY)", "Fill (CY)"]]


def _csv(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(HEAD + rows)
    return buf.getvalue().encode()


def test_reads_received_format():
    ref = read_reference(_csv([
        ["SR 5", "Mainline", "11+00", 0, 1, 2, 0, 0, 3, 4, 0, 0, 0, 0],
        ["", "", "11+50", 50, 1, 2, 1.85, 3.7, 3, 4, 5.56, 7.41, 7.41, 11.11],
        ["SR 5", "Mainline", "Subtotal", "", 2, 4, 1.85, 3.7, 6, 8, 5.56, 7.41, 7.41, 11.11],
    ]), "results.csv")
    assert ref["area_unit"] == "yd2" and len(ref["rows"]) == 2 and len(ref["subtotals"]) == 1
    r = ref["rows"][1]
    assert r["street"] == "SR 5" and r["station_ft"] == 1150
    assert r["left"]["cut_ft2"] == 9.0 and r["right"]["fill_ft2"] == 36.0      # yd² -> ft²


def test_compare_endpoint_matches_by_station_and_reports_differences(tmp_path):
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)
    secs = {s["station"]: s for s in result["sections"]}
    rows = []
    for st in ("11+00", "11+50", "12+00"):
        s = secs[st]
        sides = main.section_sides(s, "subgrade")
        # the provided results agree with ours on the left, and are 10 % higher on the right
        rows.append(["SR 1", "Mainline", st, 50, sides["left"]["cut_ft2"] / 9, sides["left"]["fill_ft2"] / 9, 0, 0,
                     sides["right"]["cut_ft2"] / 9, sides["right"]["fill_ft2"] * 1.1 / 9, 0, 0, 0, 0])
    rows.append(["SR 1", "Mainline", "99+00", 50, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0])      # not in the plans
    r = client.post(f"/api/jobs/{job_id}/compare", files={"file": ("results.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["summary"]["matched"] == 3 and rep["summary"]["missing"] == ["99+00"]
    for row in rep["rows"][:3]:
        a = row["areas"]
        assert abs(a["left_fill"]["diff"]) <= 0.05
        if a["right_fill"]["reference"] > 1:
            assert abs(a["right_fill"]["pct"] + 9.1) < 0.5          # ours is 1/1.1 of theirs
    g = rep["groups"][0]
    assert g["matched"] == 3 and g["volumes"]["fill"]["ours"] > 0
    bad = client.post(f"/api/jobs/{job_id}/compare", files={"file": ("x.csv", b"nothing here", "text/csv")})
    assert bad.status_code == 400


def test_stored_comparisons_are_served():
    client = TestClient(main.app)
    listed = client.get("/api/comparisons").json()
    names = [c["name"] for c in listed]
    assert "sr5" in names
    rep = client.get("/api/comparisons/sr5").json()
    assert rep["summary"]["referenceStations"] > 0 and rep["rows"]
    assert client.get("/api/comparisons/nope").status_code == 404
    assert client.get("/api/schemas/cross-sections").json()["title"] == "Cross-section response"
    assert client.get("/api/schemas/nope").status_code == 404
