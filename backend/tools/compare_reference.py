"""Run the pipeline on a plan set and compare it with results provided for
it (gdot_earthwork.compare); the report is what GET /api/comparisons/{name}
serves and the app's Comparison page shows.

    python -m tools.compare_reference PLANS.pdf RESULTS.xlsx comparisons/NAME.json [--title "SR 5 connector"]

Notes about the differences (what causes them) are read from
comparisons/NAME.notes.txt when it exists, one per paragraph, and shown with
the report.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time

import main
from gdot_earthwork.compare import compare, read_reference
from gdot_earthwork.plan_set import process_plan_set


def run(pdf: str, ref: str, out: str, title: str) -> dict:
    t = time.time()
    res = process_plan_set(pdf, overlays=False)
    job = main.Job(id="report", filename=os.path.basename(pdf))
    payload = main.serialize(job, res)
    with open(ref, "rb") as f:
        reference = read_reference(f.read(), ref)
    report = compare(payload["sections"], reference, res.design_surface, main.section_sides)
    report.update({
        "title": title,
        "planSet": os.path.basename(pdf),
        "referenceFile": os.path.basename(ref),
        "generated": datetime.date.today().isoformat(),
        "pipelineSeconds": round(time.time() - t, 1),
        "sections": len(payload["sections"]),
        "lowConfidence": payload["summary"]["low_confidence"],
        "ourRoads": [{"label": r["label"], "from": r["station_from"], "to": r["station_to"],
                      "fill_cy": r["volumes"][res.design_surface]["fill_cy"],
                      "cut_cy": r["volumes"][res.design_surface]["cut_cy"]} for r in payload["roads"]],
    })
    notes = os.path.splitext(out)[0] + ".notes.txt"
    if os.path.exists(notes):
        with open(notes) as f:
            report["notes"] = [" ".join(p.split()) for p in f.read().split("\n\n") if p.strip()]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    return report


if __name__ == "__main__":
    args = sys.argv[1:]
    title = "Comparison"
    if "--title" in args:
        i = args.index("--title")
        title = args[i + 1]
        args = args[:i] + args[i + 2:]
    r = run(*args[:3], title=title)
    s = r["summary"]
    print(f"matched {s['matched']}/{s['referenceStations']}  cut {s['areaCutFt2']}  fill {s['areaFillFt2']}")
    print(f"volumes cut {s['volumeCutCy']}  fill {s['volumeFillCy']}  weighted area error {s['areaWeightedErrorPct']}%")
