"""
Build accuracy.json (served at /api/accuracy, shown on the dashboard) from
the JSON files written by `tools.evaluate ... --json`.

    python -m tools.accuracy_report EVAL_DIR [--out accuracy.json]

EVAL_DIR holds one <name>.json per evaluation run; FORMATS and CHECKS below
say which run backs which dashboard card. Runs that are missing are skipped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

# One verdict card per plan-set format the user works with.
FORMATS = [
    {
        "id": "19",
        "title": "19-series",
        "format": "Scanned strips, one cross-section per page",
        "sample": "19series.pdf",
        "eval": "s19_pair",
        "reference": "Exact CAD geometry of the same 80 sheets (highway_planning1.pdf)",
    },
    {
        "id": "23",
        "title": "23-series",
        "format": "Scanned sheets, several cross-sections per sheet",
        "sample": "SR 332 mainline scans (23-series sheet layout)",
        "eval": "sr332_pair",
        "reference": "Exact CAD geometry of the same sheets (SR-332 EARTHWORK.pdf)",
    },
]

# Every evaluation, for the detailed table.
CHECKS = [
    ("s19_pair", "19-series scans", "Exact CAD geometry of the same sheets"),
    ("sr332_pair", "SR 332 scans (23-series layout)", "Exact CAD geometry of the same sheets"),
    ("hp_vector", "highway_planning1 read as an image", "Its own CAD geometry"),
    ("florence_pair", "Florence Rd scans", "Exact CAD geometry of the same sheets"),
    ("markup", "12 EARTHWORK scan sets", "Estimators' hand takeoffs on the sheets"),
]

KEEP = ("sections", "sections_scored", "median_error_pct", "p90_error_pct", "within_5pct",
        "within_10pct", "total_fill_ft2", "ref_total_fill_ft2", "total_cut_ft2",
        "ref_total_cut_ft2", "total_fill_error_pct", "total_cut_error_pct")


def _load(eval_dir: str, name: str) -> dict | None:
    path = os.path.join(eval_dir, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    stats = {k: data["stats"].get(k) for k in KEEP}
    rows = data.get("rows", [])
    if rows and "label_source" in rows[0]:
        stats["stations_read"] = sum(r.get("label_source") in ("ocr", "text") for r in rows)
        stats["stations_inferred"] = sum(r.get("label_source") == "inferred" for r in rows)
    return stats


def build(eval_dir: str) -> dict:
    formats = []
    for f in FORMATS:
        m = _load(eval_dir, f["eval"])
        if m:
            formats.append({**f, "metrics": m})
    checks = []
    for name, title, reference in CHECKS:
        m = _load(eval_dir, name)
        if m:
            checks.append({"id": name, "title": title, "reference": reference, "metrics": m})
    return {"generated": dt.date.today().isoformat(), "formats": formats, "checks": checks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("eval_dir")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "accuracy.json"))
    a = ap.parse_args(argv)
    report = build(a.eval_dir)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"wrote {os.path.normpath(a.out)}: {len(report['formats'])} formats, {len(report['checks'])} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
