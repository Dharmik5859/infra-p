"""Every calibration and cross-section response validates against the JSON
Schemas in backend/schemas, and scores / alerts follow the 85 % rule."""
import json
import os
from types import SimpleNamespace

import jsonschema
from fastapi.testclient import TestClient

import main
from gdot_earthwork.confidence import PASS_SCORE, score

from .test_api import _finished_job

SCHEMAS = os.path.join(os.path.dirname(__file__), "..", "schemas")


def _schema(name):
    with open(os.path.join(SCHEMAS, name)) as f:
        s = json.load(f)
    jsonschema.Draft202012Validator.check_schema(s)
    return jsonschema.Draft202012Validator(s)


def _polygon_ok(sh):
    pts = sh["points"]
    assert len(pts) % 2 == 0 and len(pts) >= 6
    xs, ys = pts[0::2], pts[1::2]
    assert min(xs) == 0 and min(ys) == 0
    assert abs(max(xs) - sh["dimensions"]["width"]) < 1e-6 and abs(max(ys) - sh["dimensions"]["height"]) < 1e-6


def test_responses_validate_against_schemas(tmp_path):
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)

    cal = client.get(f"/api/jobs/{job_id}/calibration").json()
    _schema("calibration.schema.json").validate(cal)
    for c in cal["calibrations"]:
        assert abs(c["pixelsPerFootX"] * 10 - c["pixelLengthX"]) < 1e-4
        assert c["gridScale"]["ftPerSquareX"] == 10 and c["gridScale"]["sourceX"] == "labels"

    validator = _schema("cross-sections.schema.json")
    for surface in ("subgrade", "finished"):
        body = client.get(f"/api/jobs/{job_id}/cross-sections", params={"surface": surface}).json()
        validator.validate(body)
        assert body["document"]["surface"] == surface
        assert len(body["crossSections"]) == result["summary"]["sections"]
        for x, s in zip(body["crossSections"], result["sections"]):
            assert x["id"] == f"xs-{s['id']}" and x["stationId"] == s["station"] and x["pageNumber"] == s["page"]
            a = x["areas"]
            # the two sides make the whole
            assert abs(a["left"]["fillSqFt"] + a["right"]["fillSqFt"] - a["total"]["fillSqFt"]) <= 0.05
            assert abs(a["total"]["fillSqFt"] - s["areas"][surface]["fill_ft2"]) <= 0.01
            for sh in x["shapes"]:
                _polygon_ok(sh)
                assert sh["crossSectionId"] == x["id"] and sh["stationId"] == x["stationId"]
            assert x["confidence"]["passed"] == (x["confidence"]["score"] >= PASS_SCORE)
        assert len(body["shapes"]) == sum(len(x["shapes"]) for x in body["crossSections"])
        assert body["summary"]["alerts"] == len(body["alerts"])
    assert client.get(f"/api/jobs/{job_id}/cross-sections", params={"surface": "nope"}).status_code == 400


def test_edits_show_in_cross_sections(tmp_path):
    client = TestClient(main.app)
    job_id, result = _finished_job(tmp_path, client)
    r = client.put(f"/api/jobs/{job_id}/edits", json={"surface": "subgrade",
                                                      "edits": {"0": {"fill_ft2": 500.0, "cut_ft2": 0}}})
    assert r.status_code == 200
    body = client.get(f"/api/jobs/{job_id}/cross-sections").json()
    _schema("cross-sections.schema.json").validate(body)
    x = body["crossSections"][0]
    assert x["edited"] is True and x["areas"]["total"]["fillSqFt"] == 500.0
    assert x["measuredAreas"]["total"]["fillSqFt"] == result["sections"][0]["measured"]["subgrade"]["fill_ft2"]


def _section(**kw):
    base = dict(station_ft=1150.0, label_source="text", label_confidence=1.0, scale={"sourceX": "labels"},
                centre_source="text", method="vector", warnings=[], zero_reason=None, fill_ft2=200.0,
                cut_ft2=10.0, page_kind="vector")
    base.update(kw)
    return SimpleNamespace(**base)


def test_confidence_score_and_alerts():
    clean = score(_section())
    assert clean["score"] == 100 and clean["passed"] and clean["alerts"] == []
    # a scan with an OCR'd station and borrowed centreline still passes
    ok = score(_section(label_source="ocr", label_confidence=0.8, method="raster", page_kind="raster",
                        centre_source="neighbour"))
    assert PASS_SCORE <= ok["score"] < 100 and ok["passed"]
    # an inferred station, assumed centreline and a bridged gap do not
    low = score(_section(label_source="inferred", centre_source="assumed",
                         warnings=["a surface was bridged across a 20 ft gap with no ink -- ..."]))
    assert low["score"] < PASS_SCORE and not low["passed"]
    assert len(low["alerts"]) == 1 and low["alerts"][0]["reasons"]
    assert sum(d["points"] for d in low["deductions"]) == 100 - low["score"]
    # an area far off both neighbours is flagged
    jump = score(_section(fill_ft2=3000.0), _section(fill_ft2=150.0), _section(fill_ft2=180.0))
    assert any(d["factor"] == "jump" for d in jump["deductions"])
