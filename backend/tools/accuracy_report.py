"""
Build accuracy.json (served at /api/accuracy, shown on the dashboard) from
the JSON files written by `tools.evaluate ... --json`.

    python -m tools.accuracy_report EVAL_DIR [--survey SURVEY_DIR] [--out accuracy.json]

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
        "second": {"eval": "sr332_markup", "reference": "the estimator's hand takeoff on the same sheets"},
    },
]

# Every evaluation, for the detailed table.
CHECKS = [
    ("s19_pair", "19-series scans", "Exact CAD geometry of the same sheets", ""),
    ("sr332_pair", "SR 332 scans (23-series layout)", "Exact CAD geometry of the same sheets",
     "Most of the scatter is three sheet-specific outliers (82+50, 135+00, 67+50)."),
    ("sr332_markup", "SR 332 scans (23-series layout)", "Estimator's hand takeoff on the sheets",
     "Estimators measure to their own conventions; a looser check than CAD geometry."),
    ("hp_vector", "highway_planning1 read as an image", "Its own CAD geometry",
     "The cut gap is a bridge 'remove below 640' line; without those stations cut is within 1 %."),
    ("florence_pair", "Florence Rd scans", "Exact CAD geometry of the same sheets",
     "Resurfacing project with tiny totals (about 70 ft² of fill), so percentages swing widely."),
    ("markup", "12 EARTHWORK scan sets", "Estimators' hand takeoffs on the sheets",
     "Estimators measure to their own conventions; a looser check than CAD geometry."),
]

# Scanned series checked section-by-section against the exact CAD drawing
# of the same sheets: the basis of the headline figures.
HEADLINE_EVALS = ["s19_pair", "sr332_pair"]
MIN_AREA = 10.0     # ft²: sections smaller than this are left out of per-section shares (as in evaluate)


def _headline(eval_dir: str) -> dict | None:
    rows, sections = [], 0
    for name in HEADLINE_EVALS:
        path = os.path.join(eval_dir, f"{name}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        rows += data["rows"]
        sections += data["stats"]["sections"]
    f, rf = sum(r["fill"] for r in rows), sum(r["ref_fill"] for r in rows)
    c, rc = sum(r["cut"] for r in rows), sum(r["ref_cut"] for r in rows)
    big = [r for r in rows if r["ref_fill"] + r["ref_cut"] >= MIN_AREA]
    err = sorted((abs(r["fill"] - r["ref_fill"]) + abs(r["cut"] - r["ref_cut"])) / (r["ref_fill"] + r["ref_cut"])
                 for r in big)
    share = lambda t: round(100 * sum(e <= t for e in err) / len(err), 1)
    pct = lambda a, b: round(100 * (a - b) / b, 2)
    return {
        "basis": "19-series and 23-series-layout scans, every section compared with the exact CAD drawing of the same sheet",
        "sections_checked": sections,
        "sections_found_and_stationed": len(rows),
        "volume_error_pct": pct(f + c, rf + rc),
        "fill_error_pct": pct(f, rf),
        "cut_error_pct": pct(c, rc),
        "sections_scored": len(big),
        "within_10pct": share(0.10),
        "within_25pct": share(0.25),
        "median_error_pct": round(100 * err[len(err) // 2], 1),
    }


def _scale(survey_dir: str | None) -> dict | None:
    """Throughput over every plan set in the dataset (tools: survey run)."""
    if not survey_dir or not os.path.isdir(survey_dir):
        return None
    recs = []
    for name in sorted(os.listdir(survey_dir)):
        if name.endswith(".json"):
            with open(os.path.join(survey_dir, name), encoding="utf-8") as fh:
                recs.append(json.load(fh))
    ok = [r for r in recs if "error" not in r]
    if not ok:
        return None
    pages = sum(r["pages"] for r in ok)
    secs = sum(r["seconds"] for r in ok)
    return {
        "plan_sets": len(recs),
        "plan_sets_processed": len(ok),
        "pages": pages,
        "cross_section_pages": sum(r["xs_pages"] for r in ok),
        "sections": sum(r["sections"] for r in ok),
        "seconds": round(secs),
        "pages_per_minute": round(60 * pages / secs) if secs else None,
    }


# Which evaluation checks which scanned plan set, best reference first.
PAIR_EVALS = {          # scan file -> evaluation against the CAD drawing of the same sheets
    "19series.pdf": "s19_pair",
    "SR 332  - MAINLINE.pdf": "sr332_pair",
    "Florence RD.pdf": "florence_pair",
    "PERRY CREEK RD- TAKEOFF EARTHWORK.pdf": "perry_pair",
    "SR 70 - CROSS SECTION.pdf": "sr70_pair",
    "WEEB CREEK - EARTHWORK.pdf": "webb_pair",
}
MARKUP_EVALS = ["markup", "mib_markup"]     # rows carry their file name


def _stats(rows: list[dict]) -> dict:
    """Totals and per-section shares for one plan set's checked sections."""
    f, rf = sum(r["fill"] for r in rows), sum(r["ref_fill"] for r in rows)
    c, rc = sum(r["cut"] for r in rows), sum(r["ref_cut"] for r in rows)
    big = [r for r in rows if r["ref_fill"] + r["ref_cut"] >= MIN_AREA]
    err = sorted((abs(r["fill"] - r["ref_fill"]) + abs(r["cut"] - r["ref_cut"])) / (r["ref_fill"] + r["ref_cut"])
                 for r in big)
    pct = lambda a, b: round(100 * (a - b) / b, 1) if b >= MIN_AREA else None
    share = lambda t: round(100 * sum(e <= t for e in err) / len(err), 1) if err else None
    return {
        "sections_checked": len(rows), "sections_scored": len(big),
        "fill_error_pct": pct(f, rf), "cut_error_pct": pct(c, rc),
        "volume_error_pct": pct(f + c, rf + rc),
        "within_10pct": share(0.10), "within_25pct": share(0.25),
        "median_error_pct": round(100 * err[len(err) // 2], 1) if err else None,
    }


def _plan_sets(eval_dir: str, survey_dir: str | None) -> list[dict]:
    """One entry per PDF the survey ran: what was found, and -- where a
    reference exists -- how close the takeoff came."""
    if not survey_dir or not os.path.isdir(survey_dir):
        return []
    rows_by_file: dict[str, tuple[str, list]] = {}
    for name in MARKUP_EVALS:
        path = os.path.join(eval_dir, f"{name}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for r in json.load(fh)["rows"]:
                    rows_by_file.setdefault(r["file"], ("estimator", []))[1].append(r)
    for fname, ev in PAIR_EVALS.items():                    # CAD drawing beats an estimator
        path = os.path.join(eval_dir, f"{ev}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                rows_by_file[fname] = ("cad", json.load(fh)["rows"])
    out = []
    for name in sorted(os.listdir(survey_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(survey_dir, name), encoding="utf-8") as fh:
            r = json.load(fh)
        fname = os.path.basename(r["file"])
        entry = {"file": fname, "folder": os.path.dirname(r["file"]) or None}
        if "error" in r:
            entry["error"] = r["error"]
            out.append(entry)
            continue
        vector = "vector" in r.get("kinds", []) and "raster" not in r.get("kinds", [])
        entry.update({
            "kind": "CAD drawing" if vector else "Scan",
            "pages": r["pages"], "sections": r["sections"],
            "stations_read": r["text"] + r["ocr"], "stations_inferred": r["inferred"],
            "no_earthwork": r["zero"], "seconds": r["seconds"],
        })
        if fname in rows_by_file and not vector:
            ref, rows = rows_by_file[fname]
            entry["reference"] = ref
            entry["check"] = _stats(rows)
        out.append(entry)
    order = {"cad": 0, "estimator": 1}
    out.sort(key=lambda e: (order.get(e.get("reference"), 2), e.get("kind") != "Scan", e["file"].lower()))
    return out


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


def build(eval_dir: str, survey_dir: str | None = None) -> dict:
    formats = []
    for f in FORMATS:
        m = _load(eval_dir, f["eval"])
        if not m:
            continue
        card = {k: v for k, v in f.items() if k != "second"}
        card["metrics"] = m
        second = f.get("second")
        if second and (m2 := _load(eval_dir, second["eval"])):
            card["second"] = {"reference": second["reference"], "metrics": m2}
        formats.append(card)
    checks = []
    for name, title, reference, note in CHECKS:
        m = _load(eval_dir, name)
        if m:
            checks.append({"id": name, "title": title, "reference": reference, "note": note, "metrics": m})
    return {"generated": dt.date.today().isoformat(), "headline": _headline(eval_dir),
            "scale": _scale(survey_dir), "formats": formats, "checks": checks,
            "plan_sets": _plan_sets(eval_dir, survey_dir)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("eval_dir")
    ap.add_argument("--survey", help="directory of survey results (one JSON per plan set)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "accuracy.json"))
    a = ap.parse_args(argv)
    report = build(a.eval_dir, a.survey)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"wrote {os.path.normpath(a.out)}: {len(report['formats'])} formats, {len(report['checks'])} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
