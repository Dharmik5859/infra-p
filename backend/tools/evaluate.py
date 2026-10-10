"""
Measure the pipeline's error rate against independent references.

Three kinds of reference are supported, because no single one exists for
every sheet format:

  markup   Scanned sheets that an estimator has already taken off by hand:
           the PDF carries a transparent markup layer with cut shaded red
           and fill shaded green. The pipeline only ever sees the scan
           underneath; the shading is measured here as the human answer.

  vector   Vector CAD exports. The surfaces are read exactly from the
           drawing's strokes; the pixel tracer is then run on a rendering
           of the same page and compared. This isolates raster-tracing error.

  pair     A scanned PDF and the vector PDF of the same sheets (matched by
           station). Scores the full scan pipeline -- OCR'd stations
           included -- against exact geometry.

Usage:
  python -m tools.evaluate markup SCAN.pdf [SCAN2.pdf ...]
  python -m tools.evaluate vector VECTOR.pdf
  python -m tools.evaluate pair SCAN.pdf VECTOR.pdf
Add --json OUT.json to save every per-section comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import pymupdf as fitz
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gdot_earthwork.config import get_config                     # noqa: E402
from gdot_earthwork.plan_set import process_plan_set             # noqa: E402

MIN_AREA = 10.0    # ft^2: below this, relative error is noise -- report absolute


# ----------------------------------------------------------- human markup

def _markup_layer(doc, page):
    # Multi-page files often list every page's images in one shared resource
    # table; only an image the page actually places is this page's markup.
    for info in page.get_images(full=True):
        if info[1] and page.get_image_rects(info[0]):
            rgb = fitz.Pixmap(doc, info[0])
            a = fitz.Pixmap(doc, info[1])
            if rgb.n != 3:
                rgb = fitz.Pixmap(fitz.csRGB, rgb)
            arr = np.frombuffer(rgb.samples, np.uint8).reshape(rgb.h, rgb.w, rgb.n)[..., :3]
            alpha = np.frombuffer(a.samples, np.uint8).reshape(a.h, a.w)
            return arr, alpha
    return None, None


def markup_areas(doc, sec) -> tuple[float, float] | None:
    rgb, alpha = _markup_layer(doc, doc[sec.page - 1])
    if rgb is None:
        return None
    if sec.rotation:      # the page was read turned; turn the markup the same way
        rgb, alpha = np.rot90(rgb, sec.rotation), np.rot90(alpha, sec.rotation)
    top, bottom, left, right = sec.bbox
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb[top:bottom, left:right]), cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    on = alpha[top:bottom, left:right] > 30
    red = on & (s > 60) & (v > 80) & ((h < 10) | (h > 165))
    green = on & (s > 40) & (v > 60) & (h >= 35) & (h <= 100)
    px = sec.px_per_ft[0] * sec.px_per_ft[1]
    return float(green.sum() / px), float(red.sum() / px)


# ------------------------------------------------------------------ stats

def compare(rows: list[dict]) -> dict:
    """rows: dicts with fill/cut (pipeline) and ref_fill/ref_cut."""
    big = [r for r in rows if r["ref_fill"] + r["ref_cut"] >= MIN_AREA]
    rel = np.array([(abs(r["fill"] - r["ref_fill"]) + abs(r["cut"] - r["ref_cut"]))
                    / (r["ref_fill"] + r["ref_cut"]) for r in big])
    small = [r for r in rows if r["ref_fill"] + r["ref_cut"] < MIN_AREA]
    small_abs = np.array([abs(r["fill"] - r["ref_fill"]) + abs(r["cut"] - r["ref_cut"]) for r in small])
    tf, tc = sum(r["fill"] for r in rows), sum(r["cut"] for r in rows)
    rf, rc = sum(r["ref_fill"] for r in rows), sum(r["ref_cut"] for r in rows)
    out = {
        "sections": len(rows),
        "sections_scored": len(big),
        "median_error_pct": round(float(np.median(rel)) * 100, 1) if len(rel) else None,
        "p90_error_pct": round(float(np.percentile(rel, 90)) * 100, 1) if len(rel) else None,
        "within_5pct": round(float((rel <= 0.05).mean()) * 100, 1) if len(rel) else None,
        "within_10pct": round(float((rel <= 0.10).mean()) * 100, 1) if len(rel) else None,
        "small_sections": len(small),
        "small_median_abs_ft2": round(float(np.median(small_abs)), 2) if len(small) else None,
        "total_fill_ft2": round(tf, 1), "ref_total_fill_ft2": round(rf, 1),
        "total_cut_ft2": round(tc, 1), "ref_total_cut_ft2": round(rc, 1),
        "total_fill_error_pct": round((tf - rf) / rf * 100, 1) if rf else None,
        "total_cut_error_pct": round((tc - rc) / rc * 100, 1) if rc else None,
    }
    return out


def _print(title: str, stats: dict, rows: list[dict], worst: int = 8) -> None:
    print(f"\n=== {title}")
    for k, v in stats.items():
        print(f"  {k:24s} {v}")
    big = [r for r in rows if r["ref_fill"] + r["ref_cut"] >= MIN_AREA]
    big.sort(key=lambda r: -(abs(r["fill"] - r["ref_fill"]) + abs(r["cut"] - r["ref_cut"]))
             / (r["ref_fill"] + r["ref_cut"]))
    if big:
        print(f"  worst sections:")
        for r in big[:worst]:
            print(f"    p{r['page']:<4} {str(r['station']):>10}  fill {r['fill']:8.1f} vs {r['ref_fill']:8.1f}"
                  f"   cut {r['cut']:8.1f} vs {r['ref_cut']:8.1f}")


def _row(sec, ref_fill, ref_cut, **extra) -> dict:
    return dict(page=sec.page, station=sec.station_label, fill=sec.fill_ft2, cut=sec.cut_ft2,
                ref_fill=round(ref_fill, 2), ref_cut=round(ref_cut, 2), **extra)


# ------------------------------------------------------------------ modes

def run_markup(paths: list[str], max_pages: int | None = None, cfg=None) -> tuple[dict, list[dict]]:
    rows = []
    for p in paths:
        pages = list(range(1, max_pages + 1)) if max_pages else None
        res = process_plan_set(p, cfg, overlays=False, pages=pages)
        doc = fitz.open(p)
        marked = 0
        for sec in res.sections:
            got = markup_areas(doc, sec)
            if got is None:
                continue
            f, c = got
            if f + c < 1.0:
                continue          # estimator didn't take this section off
            marked += 1
            rows.append(_row(sec, f, c, file=Path(p).name))
        print(f"{Path(p).name}: {len(res.sections)} sections found, {marked} with markup")
    return compare(rows), rows


def run_vector(path: str) -> tuple[dict, list[dict]]:
    cfg = get_config()
    vec = process_plan_set(path, cfg, overlays=False)
    ras = process_plan_set(path, replace(cfg, force_raster=True), overlays=False)
    key = lambda s: (s.page, s.index)
    ref = {key(s): s for s in vec.sections if s.method == "vector"}
    rows = [_row(s, ref[key(s)].fill_ft2, ref[key(s)].cut_ft2) for s in ras.sections if key(s) in ref]
    print(f"{Path(path).name}: {len(vec.sections)} sections, {len(ref)} traced from vector strokes")
    return compare(rows), rows


def run_pair(scan: str, vector: str) -> tuple[dict, list[dict]]:
    a = process_plan_set(scan, overlays=False)
    b = process_plan_set(vector, overlays=False)
    by_station: dict[float, list] = {}
    for s in b.sections:
        if s.station_ft is not None:
            by_station.setdefault(round(s.station_ft, 1), []).append(s)
    rows, unmatched = [], 0
    for s in a.sections:
        cands = by_station.get(round(s.station_ft, 1)) if s.station_ft is not None else None
        if not cands:
            unmatched += 1
            continue
        # the same station can appear in several sheet series; compare with the
        # series this scan was made from (the closest one)
        r = min(cands, key=lambda c: abs(c.fill_ft2 - s.fill_ft2) + abs(c.cut_ft2 - s.cut_ft2))
        rows.append(_row(s, r.fill_ft2, r.cut_ft2, label_source=s.label_source))
    labelled = sum(1 for s in a.sections if s.label_source in ("ocr", "text"))
    print(f"{Path(scan).name}: {len(a.sections)} sections ({labelled} labels read, "
          f"{sum(1 for s in a.sections if s.label_source == 'inferred')} inferred); "
          f"matched {len(rows)} to {Path(vector).name}, {unmatched} unmatched")
    return compare(rows), rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["markup", "vector", "pair"])
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--max-pages", type=int, help="markup mode: only the first N pages of each file")
    args = ap.parse_args(argv)
    if args.mode == "markup":
        stats, rows = run_markup(args.pdfs, args.max_pages)
    elif args.mode == "vector":
        stats, rows = run_vector(args.pdfs[0])
    else:
        stats, rows = run_pair(args.pdfs[0], args.pdfs[1])
    _print(f"{args.mode}: {', '.join(Path(p).name for p in args.pdfs)}", stats, rows)
    if args.json:
        Path(args.json).write_text(json.dumps({"stats": stats, "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
