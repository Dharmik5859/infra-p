"""Validate stages.calibrate on real sheets: for every PDF given, read each
cross-section's feet per grid square on both axes and report what was found
and how (axis labels, OCR or assumed), alongside the sheet's printed scale
note where it has one.

    python -m tools.calibration_check OUT.json PDF [PDF ...] [--pages N]

N limits the cross-section pages read per PDF (default 6).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter

import pymupdf as fitz

from gdot_earthwork.calibration import parse_scale_notes
from gdot_earthwork.config import get_config
from gdot_earthwork.stages import calibrate, detect, ingest


def check(path: str, max_pages: int = 6) -> dict:
    cfg = get_config()
    doc = fitz.open(path)
    rows, used, t0 = [], 0, time.time()
    for i in range(len(doc)):
        if used >= max_pages:
            break
        img = ingest(doc, i, cfg)
        if img is None:
            continue
        frames, img = detect(img, cfg)
        if not frames:
            continue
        used += 1
        cache: dict = {}
        notes = parse_scale_notes(doc[i].get_text())
        for f in frames:
            sc = calibrate(f, img, cfg, cache)
            rows.append({"page": i + 1, "station": f.station_label, "kind": img.kind, **sc.as_dict(),
                         "centre": sc.centre_source, "note": notes[0] if notes else None})
    doc.close()
    tally = Counter((r["ftPerSquareX"], r["ftPerSquareY"], r["sourceX"], r["sourceY"]) for r in rows)
    return {"file": path, "sections": len(rows), "seconds": round(time.time() - t0, 1),
            "scales": [{"ftX": k[0], "ftY": k[1], "sourceX": k[2], "sourceY": k[3], "sections": n}
                       for k, n in tally.most_common()],
            "rows": rows}


def main(argv: list[str]) -> None:
    pages = 6
    if "--pages" in argv:
        j = argv.index("--pages")
        pages = int(argv[j + 1])
        argv = argv[:j] + argv[j + 2:]
    out, paths = argv[0], argv[1:]
    report = []
    for p in paths:
        r = check(p, pages)
        report.append(r)
        print(f"{r['sections']:4d} sections {r['seconds']:6.1f}s  {p.rsplit('/', 1)[-1]}")
        for s in r["scales"]:
            print(f"        {s['ftX']:>5} x {s['ftY']:<5} ft/square  x:{s['sourceX']:<8} y:{s['sourceY']:<8} {s['sections']}")
    json.dump(report, open(out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1:])
