"""
Compare a takeoff with results provided for the same plan set (an
estimator's cross-section spreadsheet): section by section and volume by
volume, recording every difference.

Reference format (the "Crossections" sheet as received): one row per
station --

    Street | Stage | Station Number | Delta |
    Left:  Cut Area (yd²) | Fill Area (yd²) | Cut Vol (CY) | Fill Vol (CY) |
    Right: Cut Area (yd²) | Fill Area (yd²) | Cut Vol (CY) | Fill Vol (CY) |
    Total Volume: Cut (CY) | Fill (CY)

with "Subtotal" rows closing each street / stage. Areas in yd² are turned
into ft² (x 9); a header saying ft² is taken as is. CSV files with the same
columns work too.

Our sections are matched to reference rows by station (within MATCH_FT,
nearest first, each section used once). Volumes are compared two ways: the
reference's own totals against ours over the same stations (average end
area on our areas, with the reference's station sequence -- isolating the
area differences), and per street / stage group.
"""
from __future__ import annotations

import csv
import io
import re

from .pages import parse_station

MATCH_FT = 1.0
FT2_PER_YD2 = 9.0
CF_PER_CY = 27.0


# ------------------------------------------------------------------ reading

def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return 0.0


def _rows_from_xlsx(data: bytes) -> list[list]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = next((w for w in wb.worksheets if "cross" in w.title.lower()), wb.worksheets[0])
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _rows_from_csv(data: bytes) -> list[list]:
    return [list(r) for r in csv.reader(io.StringIO(data.decode("utf-8-sig", "ignore")))]


def read_reference(data: bytes, filename: str = "") -> dict:
    """{rows: [{street, stage, station, station_ft, delta, left/right: {cut_ft2, fill_ft2, cut_cy, fill_cy},
    cut_cy, fill_cy}], subtotals: [...], area_unit}"""
    is_xlsx = data[:2] == b"PK" or filename.lower().endswith((".xlsx", ".xlsm"))
    raw = _rows_from_xlsx(data) if is_xlsx else _rows_from_csv(data)
    head = " ".join(str(c) for r in raw[:3] for c in r if c)
    unit = "ft2" if re.search(r"ft²|ft2|sq\.? ?ft", head, re.I) and not re.search(r"yd²|yd2|sq\.? ?yd", head, re.I) else "yd2"
    k = 1.0 if unit == "ft2" else FT2_PER_YD2
    rows, subtotals = [], []
    street = stage = None
    for r in raw:
        r = list(r) + [None] * (14 - len(r))
        label = str(r[2]).strip() if r[2] is not None else ""
        street = str(r[0]).strip() if r[0] not in (None, "") else street
        stage = str(r[1]).strip() if r[1] not in (None, "") else stage
        side = lambda o: {"cut_ft2": round(_num(r[o]) * k, 2), "fill_ft2": round(_num(r[o + 1]) * k, 2),
                          "cut_cy": _num(r[o + 2]), "fill_cy": _num(r[o + 3])}
        if label.lower().startswith("subtotal"):
            subtotals.append({"street": street, "stage": stage, "left": side(4), "right": side(8),
                              "cut_cy": _num(r[12]), "fill_cy": _num(r[13])})
            continue
        ft = parse_station(label)
        if ft is None:
            continue
        rows.append({"street": street, "stage": stage, "station": label, "station_ft": ft, "delta": _num(r[3]),
                     "left": side(4), "right": side(8), "cut_cy": _num(r[12]), "fill_cy": _num(r[13])})
    if not rows:
        raise ValueError("No station rows found: expected Street | Stage | Station Number | Delta | Left ... columns.")
    return {"rows": rows, "subtotals": subtotals, "area_unit": unit}


# ------------------------------------------------------------------ comparing

def _pct(ours: float, ref: float) -> float | None:
    return None if abs(ref) < 1e-9 else round(100 * (ours - ref) / ref, 1)


def _diff(ours: float, ref: float) -> dict:
    return {"ours": round(ours, 2), "reference": round(ref, 2), "diff": round(ours - ref, 2), "pct": _pct(ours, ref)}


def _aea(stations: list[tuple[float, float]]) -> float:
    """Average-end-area volume (CY) over (station ft, area ft²) in order."""
    return sum((a0 + a1) / 2 * abs(s1 - s0) for (s0, a0), (s1, a1) in zip(stations, stations[1:])) / CF_PER_CY


def compare(sections: list[dict], reference: dict, surface: str, sides) -> dict:
    """`sections`: the job's API sections (current areas, edits applied);
    `sides(sec, surface)` their left / right split."""
    pool = [s for s in sections if s["station_ft"] is not None]
    used: set[int] = set()
    # the main road's stations claim our sections first: a station drawn on
    # one sheet can appear in two groups (Mainline and Driveways)
    size = {}
    for r in reference["rows"]:
        size[(r["street"], r["stage"])] = size.get((r["street"], r["stage"]), 0) + 1
    order = sorted(range(len(reference["rows"])),
                   key=lambda i: -size[(reference["rows"][i]["street"], reference["rows"][i]["stage"])])
    by_index: dict[int, dict] = {}
    for i in order:
        ref = reference["rows"][i]
        near = sorted((abs(s["station_ft"] - ref["station_ft"]), s["id"]) for s in pool if s["id"] not in used)
        match = next((sid for d, sid in near if d <= MATCH_FT), None)
        row = {"street": ref["street"], "stage": ref["stage"], "station": ref["station"],
               "stationFt": ref["station_ft"], "sectionId": match}
        if match is None:
            row["status"] = "missing"
            row["reference"] = {"left": ref["left"], "right": ref["right"]}
            by_index[i] = row
            continue
        used.add(match)
        sec = next(s for s in sections if s["id"] == match)
        sd = sides(sec, surface) or {"left": {"cut_ft2": 0, "fill_ft2": 0}, "right": {"cut_ft2": 0, "fill_ft2": 0}}
        row.update(status="matched", page=sec["page"], confidence=(sec.get("confidence") or {}).get("score"))
        cells = {}
        for side in ("left", "right"):
            for kind in ("cut", "fill"):
                cells[f"{side}_{kind}"] = _diff(sd[side][f"{kind}_ft2"], ref[side][f"{kind}_ft2"])
        for kind in ("cut", "fill"):
            cells[f"total_{kind}"] = _diff(sec["areas"][surface][f"{kind}_ft2"],
                                           ref["left"][f"{kind}_ft2"] + ref["right"][f"{kind}_ft2"])
        row["areas"] = cells
        by_index[i] = row
    out_rows = [by_index[i] for i in range(len(reference["rows"]))]

    # volumes over each street / stage group's own station sequence
    groups = []
    keys = list(dict.fromkeys((r["street"], r["stage"]) for r in reference["rows"]))
    for street, stage in keys:
        refs = [r for r in reference["rows"] if (r["street"], r["stage"]) == (street, stage)]
        mine = [r for r in out_rows if (r["street"], r["stage"]) == (street, stage)]
        g = {"street": street, "stage": stage, "stations": len(refs),
             "matched": sum(r["status"] == "matched" for r in mine)}
        sub = next((t for t in reference["subtotals"] if (t["street"], t["stage"]) == (street, stage)), None)
        ref_cut = sub["cut_cy"] if sub else sum(r["cut_cy"] for r in refs)
        ref_fill = sub["fill_cy"] if sub else sum(r["fill_cy"] for r in refs)
        seq = [(r["stationFt"], r["areas"]) for r in sorted(mine, key=lambda r: r["stationFt"]) if r["status"] == "matched"]
        vol = {}
        for kind, ref_v in (("cut", ref_cut), ("fill", ref_fill)):
            ours = _aea([(ft, a[f"total_{kind}"]["ours"]) for ft, a in seq])
            # the reference's areas through the same formula: shows how its
            # own volumes were computed (driveway rows may not follow it)
            recomputed = _aea([(ft, a[f"total_{kind}"]["reference"]) for ft, a in seq])
            vol[kind] = {**_diff(ours, ref_v), "referenceRecomputed": round(recomputed, 2)}
            for side in ("left", "right"):
                ref_side = sub[side][f"{kind}_cy"] if sub else sum(r[side][f"{kind}_cy"] for r in refs)
                vol[f"{side}_{kind}"] = _diff(_aea([(ft, a[f"{side}_{kind}"]["ours"]) for ft, a in seq]), ref_side)
        g["volumes"] = vol
        groups.append(g)

    matched = [r for r in out_rows if r["status"] == "matched"]
    tot = lambda kind, who: sum(r["areas"][f"total_{kind}"][who] for r in matched)
    vtot = lambda kind, who: sum(g["volumes"][kind][who] for g in groups)
    abs_err = [abs(r["areas"][f"total_{k}"]["diff"]) for r in matched for k in ("cut", "fill")]
    ref_sum = sum(r["areas"][f"total_{k}"]["reference"] for r in matched for k in ("cut", "fill"))
    within = lambda tol: sum(1 for r in matched if all(
        abs(r["areas"][f"total_{k}"]["diff"]) <= max(tol / 100 * r["areas"][f"total_{k}"]["reference"], 5.0)
        for k in ("cut", "fill")))
    return {
        "surface": surface,
        "referenceAreaUnit": reference["area_unit"],
        "summary": {
            "referenceStations": len(reference["rows"]),
            "matched": len(matched),
            "missing": [r["station"] for r in out_rows if r["status"] == "missing"],
            "extraSections": [s["station"] for s in pool if s["id"] not in used],
            "areaCutFt2": _diff(tot("cut", "ours"), tot("cut", "reference")),
            "areaFillFt2": _diff(tot("fill", "ours"), tot("fill", "reference")),
            "volumeCutCy": _diff(vtot("cut", "ours"), vtot("cut", "reference")),
            "volumeFillCy": _diff(vtot("fill", "ours"), vtot("fill", "reference")),
            # weighted absolute error over every matched section's cut and fill
            "areaWeightedErrorPct": round(100 * sum(abs_err) / ref_sum, 1) if ref_sum else None,
            "sectionsWithin10Pct": within(10),
            "sectionsWithin25Pct": within(25),
        },
        "groups": groups,
        "rows": out_rows,
    }
