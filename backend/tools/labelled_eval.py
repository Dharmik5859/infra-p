"""
Accuracy against the estimators' labels only.

The labelled data is the estimators' own takeoff: on the EARTHWORK scans
they shaded cut red and fill green on a transparent markup layer. Nothing
else is used as a reference. For every PDF given, this

* measures the labelled area on each page (before the pipeline runs),
* runs the pipeline on the scan underneath, untouched,
* measures the label inside every section the pipeline found, and keeps
  each section the estimator labelled, with both answers.

PDFs with no red/green markup are reported as having no labels. Label
shading that falls outside every section the pipeline found is counted
(label_ft2_total vs label_ft2_in_found_sections), so a missed section
counts against the pipeline.

    python -m tools.labelled_eval OUT_DIR PDF [PDF ...]

Writes OUT_DIR/<file>.json per labelled PDF; `tools.accuracy_report
--labelled OUT_DIR` turns them into accuracy.json.
"""
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
OUT = sys.argv[1] if __name__ == "__main__" else None


def one(path):
    import numpy as np, pymupdf as fitz
    from gdot_earthwork.plan_set import process_plan_set
    from tools.evaluate import _markup_layer, label_pixels, markup_areas, _row
    name = Path(path).name
    doc = fitz.open(path)
    # labelled area on each page, whole page (before the pipeline sees anything)
    page_px = {}
    for p in doc:
        rgb, a = _markup_layer(doc, p)
        if rgb is not None:
            f, c = label_pixels(rgb, a)
            if f + c > 0:
                page_px[p.number + 1] = (float(f), float(c))
    if not page_px:
        print(f"{name}: no labels", flush=True)
        json.dump({"file": name, "path": path, "pages": len(doc), "labelled_pages": 0, "rows": []},
                  open(f"{OUT}/{name}.json", "w"), indent=1)
        return
    res = process_plan_set(path, workers=1, overlays=False)
    rows, in_sections = [], {}
    for sec in res.sections:
        got = markup_areas(doc, sec)
        if got is None:
            continue
        ppf2 = sec.px_per_ft[0] * sec.px_per_ft[1]
        in_sections.setdefault(sec.page, [0.0, ppf2])[0] += (got[0] + got[1]) * ppf2
        if got[0] + got[1] < 1.0:
            continue        # estimator did not take this section off
        rows.append(_row(sec, got[0], got[1], file=name, rotation=sec.rotation))
    ppf2s = [v[1] for v in in_sections.values()]
    med = float(np.median(ppf2s)) if ppf2s else None
    label_total = sum((f + c) / (in_sections.get(pg, [0, med])[1] or 1) for pg, (f, c) in page_px.items()) if med else None
    label_found = sum(v[0] / v[1] for v in in_sections.values())
    out = {"file": name, "path": path, "pages": len(doc), "labelled_pages": len(page_px),
           "sections_found": len(res.sections), "sections_labelled": len(rows),
           "label_ft2_total": round(label_total, 1) if label_total else None,
           "label_ft2_in_found_sections": round(label_found, 1), "rows": rows}
    json.dump(out, open(f"{OUT}/{name}.json", "w"), indent=1, default=float)
    print(f"{name}: {len(res.sections)} sections, {len(rows)} labelled", flush=True)


if __name__ == "__main__":
    paths = sorted(sys.argv[2:], key=os.path.getsize, reverse=True)
    with Pool(4) as pool:
        pool.map(one, paths, chunksize=1)
    print("LABELLED DONE", flush=True)
