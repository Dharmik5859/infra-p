"""
Calibration: how many page pixels make a foot, for every sheet of a plan
set -- and the cut / fill areas found on it as page-space shapes.

Pixels are PDF points of the page as displayed (rotation applied), i.e. the
CSS pixels of a PDF viewer at 100 % zoom (pdf.js scale 1, as a Konva canvas
over the page uses them). A sheet plotted at 1" = 20' therefore has
36 pixels per 10 ft.

Each sheet's scale comes from, in order of trust:

  grid           the cross-section grid measured on the sheet itself, with
                 the feet per square each axis read off its labels -- valid
                 however the PDF was printed or scanned;
  sheet_note     a scale note printed on that sheet (1" = 20', HORIZ / VERT);
  document_note  the scale note of the document (usually on the first page),
                 for sheets that carry neither.

A written scale holds only for a full-size plot; the grid needs no such
assumption, so where both exist the grid wins and the note is reported
alongside as a check (noteCheck, with the ratio grid / note). When every
sheet with both agrees on a ratio other than 1 -- a set printed at half
size -- the ratio is reported (printScale) and applied to the sheets that
only have a note.

Output follows the app's calibration and shape formats:

  calibration  {id, mode: "single", pageNumber, pixelLengthX/Y, realWorldLengthX/Y,
                scaleX/Y (feet per pixel), unit: "feet"} plus pixelsPerFootX/Y,
                verticalDiffers, source, and for grid sheets gridScale (ft per
                major square each axis, read off the axis labels by
                stages.calibrate)
  shape        {crossSectionType: "cut"|"fill", id, pageNumber, points: [x0, y0, x1, y1, ...]
                offsets from position2D (the shape's top-left), position2D: {x, y},
                dimensions: {width, height, depth: 0}, side: "left"|"right",
                stage, stationId, streetName, areaSqFt, crossSectionId}
"""
from __future__ import annotations

import math
import os
import re
import secrets
import shutil
import subprocess
import time

import cv2
import numpy as np
import pymupdf as fitz

from .surfaces import CANON_PPF

REAL_FT = 10.0          # calibrations are stated per 10 ft, as one major grid square
GEOMETRY_STEP = 4       # canonical columns between stored geometry points (plan_set.GEOMETRY_STEP)

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-"


def nanoid(n: int = 21) -> str:
    """A short random id like the app's (nanoid alphabet)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


# ----------------------------------------------------------- scale notes

# 1" = 20'   1 IN = 20 FT   1"=20'-0"   HORIZ 1" = 20'  VERT. 1" = 5'
_INCH_RE = re.compile(
    r"(?P<axis>HORIZ(?:ONTAL)?\.?|VERT(?:ICAL)?\.?|H:|V:)?\s*(?:SCALE\s*:?\s*)?"
    r"(?P<inch>\d+(?:\.\d+)?)\s*(?:\"|''|”|IN(?:CH)?(?:ES)?\.?)\s*=\s*"
    r"(?P<ft>\d+(?:\.\d+)?)\s*(?:'|’|FT\.?|FEET)", re.I)
# SCALE 1:240 (inches to inches)
_RATIO_RE = re.compile(r"(?P<axis>HORIZ(?:ONTAL)?\.?|VERT(?:ICAL)?\.?)?\s*SCALE\s*:?\s*1\s*:\s*(?P<n>\d{2,5})\b", re.I)


def _axis(tag: str | None) -> str:
    t = (tag or "").upper()
    return "x" if t.startswith("H") else "y" if t.startswith("V") else "xy"


def parse_scale_notes(text: str) -> list[dict]:
    """Scale statements in a page's text: [{text, axis, feet_per_inch}]."""
    out = []
    for m in _INCH_RE.finditer(text):
        inch, ft = float(m["inch"]), float(m["ft"])
        if inch > 0 and 0 < ft <= 2000:
            out.append({"text": " ".join(m.group(0).split()), "axis": _axis(m["axis"]), "feet_per_inch": ft / inch})
    for m in _RATIO_RE.finditer(text):
        out.append({"text": " ".join(m.group(0).split()), "axis": _axis(m["axis"]), "feet_per_inch": int(m["n"]) / 12})
    return out


def _page_text(page: fitz.Page, ocr: bool = True) -> str:
    text = page.get_text()
    if text.strip() or not ocr:
        return text
    # a scanned sheet: read it (once, at a modest resolution: scale notes are large print)
    if not shutil.which("tesseract"):
        return ""
    z = 2400 / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csGRAY, alpha=False)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w)
    ok, buf = cv2.imencode(".png", img)
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11"], input=buf.tobytes(), capture_output=True,
                       env={**os.environ, "OMP_THREAD_LIMIT": "1"}, timeout=120)
    return r.stdout.decode("utf-8", "ignore")


def scale_notes(doc: fitz.Document, pages: list[int], ocr_pages: set[int] = frozenset()) -> dict[int, list[dict]]:
    """Scale notes on the given pages (1-based); scanned pages are read by OCR
    only when listed in `ocr_pages` (OCR is the slow part)."""
    return {n: parse_scale_notes(_page_text(doc[n - 1], ocr=n in ocr_pages)) for n in pages if 1 <= n <= len(doc)}


def _from_notes(notes: list[dict]) -> tuple[float, float] | None:
    """Pixels per 10 ft (x, y) from a sheet's scale notes, assuming a full-size plot."""
    x = next((n for n in notes if n["axis"] in ("x", "xy")), None)
    y = next((n for n in notes if n["axis"] in ("y", "xy")), None) or x
    x = x or y
    if not x:
        return None
    px = lambda n: 72.0 / n["feet_per_inch"] * REAL_FT        # 72 points per inch
    return px(x), px(y)


# ----------------------------------------------------------- calibration

def _displayed(page: fitz.Page):
    rot = page.rotation_matrix
    return lambda p: fitz.Point(p) * rot


def _grid_px(sec, to_disp) -> tuple[float, float] | None:
    """Pixels per 10 ft along the section's own axes, from its measured grid."""
    g = sec.geometry
    if not g:
        return None
    tl, tr, bl = (to_disp(p) for p in g["frame"])
    top, bottom, left, right = sec.bbox
    width_ft = (right - left) / sec.px_per_ft[0]
    height_ft = (bottom - top) / sec.px_per_ft[1]
    if width_ft <= 0 or height_ft <= 0:
        return None
    return abs(tr - tl) / width_ft * REAL_FT, abs(bl - tl) / height_ft * REAL_FT


def _calibration(page_no: int, px_x: float, px_y: float, source: str, **extra) -> dict:
    return {
        "id": nanoid(), "mode": "single", "pageNumber": page_no,
        "pixelLengthX": round(px_x, 6), "pixelLengthY": round(px_y, 6),
        "realWorldLengthX": REAL_FT, "realWorldLengthY": REAL_FT,
        "scaleX": round(REAL_FT / px_x, 9), "scaleY": round(REAL_FT / px_y, 9),
        "unit": "feet",
        # the same scale the other way round: pixels per foot, each axis
        "pixelsPerFootX": round(px_x / REAL_FT, 6), "pixelsPerFootY": round(px_y / REAL_FT, 6),
        "verticalDiffers": abs(px_x - px_y) > 0.01 * max(px_x, px_y),
        "source": source, **extra,
    }


def _grid_scale(secs) -> dict | None:
    """What the sheet's sections say about their grid: ft per major square on
    each axis (most common reading) and how it was found (stages.calibrate)."""
    reads = [s.scale for _, s in secs if s.scale]
    if not reads:
        return None
    pick = lambda key: max({r[key] for r in reads}, key=lambda v: sum(r[key] == v for r in reads))
    return {"ftPerSquareX": pick("ftPerSquareX"), "ftPerSquareY": pick("ftPerSquareY"),
            "sourceX": pick("sourceX"), "sourceY": pick("sourceY")}


PRINT_RATIO_TOL = 0.03      # sheets must agree this closely for their print ratio to be applied


def _print_ratio(doc: fitz.Document, by_page: dict, notes: dict) -> tuple[float | None, list[int]]:
    """How the set was printed relative to its scale notes: the measured grid
    over the note's scale, on every sheet that has both. Plans are often
    printed at half size (11" x 17" from 22" x 34"), so a 1" = 10' note then
    reads 1" = 20' on the page. Only returned (and then applied to sheets that
    have a note but no grid) when it is not 1 and every such sheet agrees."""
    ratios, pages = [], []
    for page_no, secs in by_page.items():
        sheet_note = _from_notes(notes.get(page_no, []))
        if not sheet_note:
            continue
        to_disp = _displayed(doc[page_no - 1])
        grids = [g for g in (_grid_px(s, to_disp) for _, s in secs) if g]
        if grids:
            ratios.append(float(np.median([g[0] for g in grids])) / sheet_note[0])
            pages.append(page_no)
    if not ratios:
        return None, []
    med = float(np.median(ratios))
    if abs(med - 1) <= PRINT_RATIO_TOL or any(abs(r - med) > PRINT_RATIO_TOL * med for r in ratios):
        return None, []
    return round(med, 4), sorted(pages)


def _ratio_meaning(r: float | None) -> str | None:
    if not r:
        return None
    if abs(r - 0.5) <= PRINT_RATIO_TOL:
        return "printed at half size: the scale notes are for full-size sheets (e.g. 22 x 34 in printed 11 x 17 in)"
    return f"printed at {r:.0%} of the size the scale notes are written for"


# ----------------------------------------------------------- shapes

def _zones(g: dict, surface: str, centre_idx: float | None):
    """Fill / cut runs between the traced lines (page points), split at the
    centreline: [(kind, side, polygon points)]."""
    ground, top = g["ground"], g.get(surface) or g["finished"]
    tl, _, bl = g["frame"]
    v = (tl[0] - bl[0], tl[1] - bl[1])
    n = math.hypot(*v) or 1.0
    up = (v[0] / n, v[1] / n)
    out = []
    run: list[int] = []
    state = (0, None)

    def flush():
        if len(run) >= 2:
            kind = "fill" if state[0] > 0 else "cut"
            poly = [top[i] for i in run] + [ground[i] for i in reversed(run)]
            out.append((kind, state[1], poly))

    for i, (gp, tp) in enumerate(zip(ground, top)):
        sign = 0
        if gp is not None and tp is not None:
            d = (tp[0] - gp[0]) * up[0] + (tp[1] - gp[1]) * up[1]
            sign = 1 if d > 0.02 else -1 if d < -0.02 else 0
        side = None if centre_idx is None else ("left" if i < centre_idx else "right")
        if (sign, side) != state:
            flush()
            # zones touching across the centreline (or a crossing) share their boundary point
            run = [run[-1]] if run and sign and state[0] == sign else []
            state = (sign, side)
        if sign:
            run.append(i)
    flush()
    return out


def _poly_area(pts) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def _shape(kind: str, side: str | None, page_no: int, pts, px_per_ft2: float, sec_meta: dict) -> dict:
    """A cut / fill zone in the app's shape format (see the module notes)."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    flat = [round(v, 6) for p in pts for v in (p[0] - x0, p[1] - y0)]
    return {
        "crossSectionType": kind,
        "id": f"polygon-{int(time.time() * 1000)}-{nanoid(9).lower()}",
        "pageNumber": page_no,
        "points": flat,
        "position2D": {"x": round(x0, 6), "y": round(y0, 6)},
        "dimensions": {"width": round(max(xs) - x0, 6), "height": round(max(ys) - y0, 6), "depth": 0},
        "side": side,
        "stage": sec_meta["stage"],
        "stationId": sec_meta["station"],
        "streetName": sec_meta["street"],
        "areaSqFt": round(_poly_area(pts) / px_per_ft2, 2),
        "crossSectionId": sec_meta.get("id"),
    }


# ----------------------------------------------------------- the response

def build(result, pdf_path: str, filename: str, road_labels: dict[int, str] | None = None) -> dict:
    """The calibration response for a processed plan set (plan_set.PlanSetResult)."""
    road_labels = road_labels or {}
    m = re.search(r"STAGE\s*(\d+)", filename, re.I)
    stage = f"Stage {m.group(1)}" if m else None
    doc = fitz.open(pdf_path)
    try:
        by_page: dict[int, list] = {}
        for i, s in enumerate(result.sections):
            by_page.setdefault(s.page, []).append((i, s))
        # scale notes: the first page (cover / title sheet) and every cross-section
        # sheet. A scanned sheet is OCR'd only where its note is needed -- the
        # first page, and sheets whose grid could not be measured.
        note_pages = sorted({1, *by_page})
        gridless = {p for p, secs in by_page.items() if not any(s.geometry for _, s in secs)}
        notes = scale_notes(doc, note_pages, ocr_pages={1} | gridless)
        doc_note = next((n for p in note_pages for n in notes.get(p, [])), None)
        doc_note_page = next((p for p in note_pages if notes.get(p)), None)

        print_ratio, ratio_pages = _print_ratio(doc, by_page, notes)

        calibrations, shapes, uncalibrated = [], [], []
        for page_no in range(1, len(doc) + 1):
            page = doc[page_no - 1]
            to_disp = _displayed(page)
            secs = by_page.get(page_no, [])
            grids = [g for g in (_grid_px(s, to_disp) for _, s in secs) if g]
            sheet_note = _from_notes(notes.get(page_no, []))
            if sheet_note and not grids and print_ratio:
                sheet_note = (sheet_note[0] * print_ratio, sheet_note[1] * print_ratio)
            if grids:
                px = (float(np.median([g[0] for g in grids])), float(np.median([g[1] for g in grids])))
                extra = {"sections": len(secs)}
                gs = _grid_scale(secs)
                if gs:
                    extra["gridScale"] = gs
                if sheet_note:
                    extra["noteCheck"] = {"text": notes[page_no][0]["text"], "pixelLengthX": round(sheet_note[0], 4),
                                          "pixelLengthY": round(sheet_note[1], 4),
                                          "printRatio": round(px[0] / sheet_note[0], 4)}
                calibrations.append(_calibration(page_no, px[0], px[1], "grid", **extra))
            elif sheet_note:
                extra = {"printRatio": print_ratio} if print_ratio else {}
                calibrations.append(_calibration(page_no, *sheet_note, "sheet_note", note=notes[page_no][0]["text"],
                                                 **extra))
            elif secs and doc_note:
                px = _from_notes([doc_note])
                extra = {"printRatio": print_ratio} if print_ratio else {}
                if print_ratio:
                    px = (px[0] * print_ratio, px[1] * print_ratio)
                calibrations.append(_calibration(page_no, *px, "document_note", note=doc_note["text"],
                                                 notePage=doc_note_page, **extra))
            elif secs:
                uncalibrated.append(page_no)

            cal = next((c for c in calibrations if c["pageNumber"] == page_no), None)
            if not cal:
                continue
            px_per_ft2 = (cal["pixelLengthX"] / REAL_FT) * (cal["pixelLengthY"] / REAL_FT)
            for i, s in secs:
                g = s.geometry
                if not g:
                    continue
                gd = {k: ([None if p is None else tuple(to_disp(p)) for p in g[k]] if k in ("ground", "finished", "subgrade")
                          else [tuple(to_disp(p)) for p in g[k]] if k == "frame" else g[k]) for k in g}
                centre_idx = s.centre_ft * CANON_PPF / GEOMETRY_STEP if s.centre_ft is not None else None
                meta = {"stage": stage, "station": s.station_label, "street": road_labels.get(i) or s.street, "id": f"xs-{i}"}
                for kind, side, poly in _zones(gd, result.design_surface, centre_idx):
                    shapes.append(_shape(kind, side, page_no, poly, px_per_ft2, meta))

        return {
            "document": {"fileName": filename, "pages": len(doc), "crossSectionPages": len(by_page),
                         "sections": len(result.sections), "surface": result.design_surface},
            "pixelUnit": "PDF point of the page as displayed (1/72 in; a PDF viewer at 100 % zoom)",
            "documentScale": {"text": doc_note["text"], "pageNumber": doc_note_page,
                              "feetPerInch": doc_note["feet_per_inch"]} if doc_note else None,
            # the sheets' measured grids against their printed notes: how the set was printed
            "printScale": {"ratio": print_ratio, "pages": ratio_pages,
                           "meaning": _ratio_meaning(print_ratio)} if print_ratio else None,
            "calibrations": calibrations,
            "uncalibratedPages": uncalibrated,
            "shapes": shapes,
        }
    finally:
        doc.close()
