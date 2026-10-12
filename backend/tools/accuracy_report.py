"""
Build accuracy.json (served at /api/accuracy, shown on the Accuracy page and
the dashboard) from the estimators' labelled takeoffs ONLY.

    python -m tools.accuracy_report LABELLED_DIR [--out accuracy.json]

LABELLED_DIR holds one <file>.json per PDF, written by `tools.labelled_eval`.
Every number in the report is the pipeline's answer compared with the area an
estimator shaded on the same section; no other reference is used.

Staged-construction sheets ("STAGE" in the file name) are reported apart from
mainline sheets: an estimator shades only that stage's share of the work on
them, while the pipeline measures the whole section.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

MIN_AREA = 10.0     # ft²: sections smaller than this are left out of per-section shares

# The sample of each format the user works with, where a labelled copy exists.
FORMATS = [
    {"id": "23", "title": "23-series", "format": "Scanned sheets, several cross-sections per sheet",
     "file": "MOUNTAIN IND BLVD - MAINLINE EARTHWORK.pdf",
     "reference": "the estimator's labelled takeoff of the 23-series sample (Mountain Ind Blvd mainline)"},
    {"id": "19", "title": "19-series", "format": "Scanned strips, one cross-section per page",
     "file": "19series.pdf", "reference": None},
]


def stats(rows: list[dict]) -> dict:
    """Pipeline vs label over a set of labelled sections."""
    f, rf = sum(r["fill"] for r in rows), sum(r["ref_fill"] for r in rows)
    c, rc = sum(r["cut"] for r in rows), sum(r["ref_cut"] for r in rows)
    big = [r for r in rows if r["ref_fill"] + r["ref_cut"] >= MIN_AREA]
    err = sorted((abs(r["fill"] - r["ref_fill"]) + abs(r["cut"] - r["ref_cut"])) / (r["ref_fill"] + r["ref_cut"])
                 for r in big)
    pct = lambda a, b: round(100 * (a - b) / b, 1) if b >= MIN_AREA else None
    share = lambda t: round(100 * sum(e <= t for e in err) / len(err), 1) if err else None
    return {
        "sections": len(rows), "sections_scored": len(big),
        "fill_ft2": round(f, 1), "label_fill_ft2": round(rf, 1),
        "cut_ft2": round(c, 1), "label_cut_ft2": round(rc, 1),
        "fill_error_pct": pct(f, rf), "cut_error_pct": pct(c, rc),
        "total_error_pct": pct(f + c, rf + rc),
        "within_10pct": share(0.10), "within_25pct": share(0.25),
        "median_error_pct": round(100 * err[len(err) // 2], 1) if err else None,
        "p90_error_pct": round(100 * err[int(0.9 * (len(err) - 1))], 1) if err else None,
    }


def _coverage(files: list[dict]) -> float | None:
    """Share of all labelled shading that lies inside sections the pipeline found."""
    tot = sum(f.get("label_ft2_total") or 0 for f in files)
    found = sum(f.get("label_ft2_in_found_sections") or 0 for f in files)
    return round(100 * min(found, tot) / tot, 1) if tot else None


def build(labelled_dir: str) -> dict:
    runs = []
    for name in sorted(os.listdir(labelled_dir)):
        if name.endswith(".json"):
            with open(os.path.join(labelled_dir, name), encoding="utf-8") as fh:
                runs.append(json.load(fh))
    labelled = [r for r in runs if r["rows"]]
    staged = lambda r: "STAGE" in r["file"].upper()
    files = [{
        "file": r["file"], "kind": "staged" if staged(r) else "mainline",
        "pages": r.get("pages"), "labelled_pages": r.get("labelled_pages"),
        "sections_found": r.get("sections_found"), "label_found_pct": _coverage([r]), **stats(r["rows"]),
    } for r in labelled]
    files.sort(key=lambda f: (f["kind"] != "mainline", f["file"].lower()))
    rows_of = lambda runs_: [row for r in runs_ for row in r["rows"]]
    by_file = {r["file"]: r for r in labelled}
    formats = []
    for fm in FORMATS:
        card = dict(fm)
        if fm["file"] in by_file:
            card["metrics"] = stats(by_file[fm["file"]]["rows"])
        formats.append(card)
    mainline, stages = [r for r in labelled if not staged(r)], [r for r in labelled if staged(r)]
    return {
        "generated": dt.date.today().isoformat(),
        "basis": "estimator_labels",
        "overall": {**stats(rows_of(labelled)), "files": len(labelled), "label_found_pct": _coverage(labelled)},
        "groups": [
            {"id": "mainline", "title": "Mainline sheets", **stats(rows_of(mainline)), "files": len(mainline),
             "label_found_pct": _coverage(mainline),
             "note": "The estimator shaded the whole section, as the pipeline measures it: the like-for-like comparison."},
            {"id": "staged", "title": "Staged-construction sheets", **stats(rows_of(stages)), "files": len(stages),
             "label_found_pct": _coverage(stages),
             "note": "The estimator shaded only that stage's share of the work; the pipeline measures the whole "
                     "section and does not yet separate construction stages."},
        ],
        "formats": formats,
        "files": files,
        "unlabelled": sorted(r["file"] for r in runs if not r["rows"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labelled_dir")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "accuracy.json"))
    a = ap.parse_args(argv)
    report = build(a.labelled_dir)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    o = report["overall"]
    print(f"wrote {os.path.normpath(a.out)}: {o['files']} labelled PDFs, {o['sections']} sections; "
          f"total {o['total_error_pct']:+.1f}%, fill {o['fill_error_pct']:+.1f}%, cut {o['cut_error_pct']:+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
