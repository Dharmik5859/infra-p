"""
The original plan-set PDF, annotated with the takeoff.

Every page of the uploaded PDF is kept exactly as it was (same pages, same
size, same vector or scanned content). On top of each measured
cross-section the export draws, as real PDF vector graphics:

* fill (green) and cut (red) shading between existing ground and the
  proposed surface, with the traced lines,
* a label with the station and the fill / cut areas in use -- hand-edited
  values marked as such, with the measured values alongside.

Summary pages are appended at the end, the same size as the first page:
totals, volumes per road and every hand edit.
"""
from __future__ import annotations

import math
import time

import pymupdf as fitz

FILL = (30 / 255, 142 / 255, 62 / 255)       # #1E8E3E
CUT = (217 / 255, 48 / 255, 37 / 255)        # #D93025
GROUND = (26 / 255, 115 / 255, 232 / 255)    # #1A73E8
DESIGN = (0.13, 0.13, 0.14)
EDITED = (176 / 255, 96 / 255, 0)            # #B06000
INK = (0.13, 0.13, 0.14)
MUTED = (0.37, 0.39, 0.41)


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _len(v):
    return math.hypot(v[0], v[1]) or 1.0


def _frame_axes(geom):
    """Origin and unit vectors of the frame on the page: x along the
    section's offset axis, y downward on the drawing, plus its size."""
    tl, tr, bl = geom["frame"]
    vx, vy = _sub(tr, tl), _sub(bl, tl)
    w, h = _len(vx), _len(vy)
    return tl, (vx[0] / w, vx[1] / w), (vy[0] / h, vy[1] / h), w, h


def _at(origin, ex, ey, a, b):
    return origin[0] + ex[0] * a + ey[0] * b, origin[1] + ex[1] * a + ey[1] * b


def _rect(origin, ex, ey, a0, b0, a1, b1) -> fitz.Rect:
    pts = [_at(origin, ex, ey, a, b) for a in (a0, a1) for b in (b0, b1)]
    return fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts),
                     max(p[0] for p in pts), max(p[1] for p in pts))


def _text_rotate(ex) -> int:
    """insert_textbox `rotate` (counter-clockwise, unrotated page space) that
    makes text run along the section's offset axis."""
    ang = math.degrees(math.atan2(ex[1], ex[0]))          # clockwise, y down
    return int(round(-ang / 90.0)) % 4 * 90


def _shade(page: fitz.Page, geom: dict, surface: str) -> None:
    ground, top = geom["ground"], geom[surface]
    _, _, ey, _, _ = _frame_axes(geom)
    up = (-ey[0], -ey[1])
    shape = page.new_shape()
    run: list[int] = []
    run_sign = 0

    def flush():
        if len(run) >= 2:
            pts = [fitz.Point(top[i]) for i in run] + [fitz.Point(ground[i]) for i in reversed(run)]
            shape.draw_polyline(pts)
            shape.finish(color=None, fill=FILL if run_sign > 0 else CUT, fill_opacity=0.38, closePath=True)

    for i, (g, t) in enumerate(zip(ground, top)):
        sign = 0
        if g is not None and t is not None:
            d = (t[0] - g[0]) * up[0] + (t[1] - g[1]) * up[1]   # +: proposed above ground
            sign = 1 if d > 0.02 else -1 if d < -0.02 else 0
        if sign != run_sign:
            flush()
            run = [run[-1]] if run and sign else []          # share the crossing point
            run_sign = sign
        if sign:
            run.append(i)
    flush()

    def polyline(pts, colour, width):
        seg = []
        for p in pts + [None]:
            if p is None:
                if len(seg) > 1:
                    shape.draw_polyline([fitz.Point(q) for q in seg])
                    shape.finish(color=colour, width=width, closePath=False)
                seg = []
            else:
                seg.append(p)

    polyline(ground, GROUND, 0.7)
    polyline(top, DESIGN, 0.6)
    shape.commit(overlay=True)


def _label(page: fitz.Page, geom: dict, sec: dict, surface: str, edited: bool) -> None:
    origin, ex, ey, w, h = _frame_axes(geom)
    fs = max(4.5, min(10.0, h * 0.04))
    area = sec["areas"][surface]
    lines = [(f"STA {sec['station'] or '?'}", "hebo", INK),
             (f"FILL {area['fill_ft2']:,.1f} ft²   CUT {area['cut_ft2']:,.1f} ft²", "helv", INK)]
    if edited:
        m = sec["measured"][surface]
        lines.append((f"EDITED - measured fill {m['fill_ft2']:,.1f}, cut {m['cut_ft2']:,.1f}", "helv", EDITED))
    text_w = max(fitz.get_text_length(t, fontname=f, fontsize=fs) for t, f, _ in lines)
    line_h = fs * 1.3
    pad = fs * 0.5
    box_w, box_h = text_w + 2 * pad + fs, line_h * len(lines) + 2 * pad
    m0 = fs * 0.6                                    # gap from the frame corner
    page.draw_rect(_rect(origin, ex, ey, m0, m0, m0 + box_w, m0 + box_h),
                   color=EDITED if edited else INK, fill=(1, 1, 1), width=0.6, fill_opacity=0.92, overlay=True)
    rot = _text_rotate(ex)
    for k, (text, font, colour) in enumerate(lines):
        b0 = m0 + pad + k * line_h
        # generous box so the text never overflows (an overflowing textbox draws nothing)
        r = _rect(origin, ex, ey, m0 + pad, b0 - fs * 0.15, m0 + box_w + fs * 2, b0 + line_h + fs * 0.6)
        page.insert_textbox(r, text, fontsize=fs, fontname=font, color=colour, rotate=rot)


def _summary_pages(doc: fitz.Document, title: str, summary: dict) -> None:
    W, H = doc[0].rect.width, doc[0].rect.height
    W, H = max(W, H), min(W, H)          # landscape summary, like the sheets
    margin = 48
    line_h = 15
    rows: list[tuple] = []               # (kind, cells)

    def new_page():
        p = doc.new_page(width=W, height=H)
        p.draw_rect(fitz.Rect(0, 0, W, 6), color=None, fill=GROUND)
        x = 0
        for c in (GROUND, CUT, (249 / 255, 171 / 255, 0), FILL):
            p.draw_rect(fitz.Rect(margin + x, 22, margin + x + 18, 26), color=None, fill=c)
            x += 22
        p.insert_text((margin, 48), "Earthwork takeoff", fontsize=20, fontname="hebo", color=INK)
        p.insert_text((margin, 66), title, fontsize=10, fontname="helv", color=MUTED)
        return p, 96

    page, y = new_page()
    t = summary["totals"]
    tiles = [("CUT", f"{t['cut_cy']:,.0f} cy", CUT), ("FILL", f"{t['fill_cy']:,.0f} cy", FILL),
             ("NET", f"{t['net_cy']:+,.0f} cy", GROUND), ("SECTIONS", f"{summary['sections']}", INK)]
    tw = (W - 2 * margin - 3 * 12) / 4
    for i, (k, v, c) in enumerate(tiles):
        x0 = margin + i * (tw + 12)
        page.draw_rect(fitz.Rect(x0, y, x0 + tw, y + 58), color=(0.85, 0.86, 0.88), fill=(0.97, 0.97, 0.98), width=0.6)
        page.draw_rect(fitz.Rect(x0, y, x0 + 4, y + 58), color=None, fill=c)
        page.insert_text((x0 + 14, y + 20), k, fontsize=8.5, fontname="hebo", color=MUTED)
        page.insert_text((x0 + 14, y + 44), v, fontsize=18, fontname="hebo", color=c)
    y += 80
    notes = [f"Measured to {summary['surface_label']}. Volumes by the average-end-area method between consecutive stations.",
             f"Roads counted: {summary['counted']} of {len(summary['roads'])}. "
             f"Sections edited by hand: {len(summary['edits'])}. Generated {time.strftime('%Y-%m-%d %H:%M')}."]
    for n in notes:
        page.insert_text((margin, y), n, fontsize=9, fontname="helv", color=MUTED)
        y += 13
    y += 12

    cols = [("Road", 0), ("Stations", 120), ("Sections", 300), ("Counted", 370),
            ("Cut (cy)", 470), ("Fill (cy)", 570), ("Net (cy)", 670)]
    for r in summary["roads"]:
        rows.append(("road", [r["label"], f"{r['from']} – {r['to']}", str(r["sections"]),
                              "yes" if r["counted"] else "no (repeat)" if r["repeat"] else "no",
                              f"{r['cut_cy']:,.0f}", f"{r['fill_cy']:,.0f}", f"{r['net_cy']:+,.0f}"]))
    if summary["edits"]:
        rows.append(("gap", []))
        rows.append(("h2", ["Hand-edited sections"]))
        rows.append(("head", ["Station", "Page", "", "", "Cut ft² (measured)", "Fill ft² (measured)", ""]))
        for e in summary["edits"]:
            rows.append(("edit", [e["station"] or "?", str(e["page"]), "", "",
                                  f"{e['cut']:,.1f} ({e['m_cut']:,.1f})", f"{e['fill']:,.1f} ({e['m_fill']:,.1f})", ""]))

    def header(p, y):
        p.draw_rect(fitz.Rect(margin, y - 11, W - margin, y + 5), color=None, fill=(0.95, 0.95, 0.96))
        for name, x in cols:
            p.insert_text((margin + 6 + x, y), name, fontsize=8.5, fontname="hebo", color=MUTED)
        return y + line_h + 2

    y = header(page, y)
    for kind, cells in rows:
        if y > H - margin:
            page, y = new_page()
            y = header(page, y)
        if kind == "gap":
            y += 8
            continue
        if kind == "h2":
            page.insert_text((margin, y + 4), cells[0], fontsize=12, fontname="hebo", color=INK)
            y += line_h + 6
            continue
        if kind == "head":
            page.draw_rect(fitz.Rect(margin, y - 11, W - margin, y + 5), color=None, fill=(0.95, 0.95, 0.96))
        for (name, x), text in zip(cols, cells):
            colour = CUT if name.startswith("Cut") and kind != "head" else \
                FILL if name.startswith("Fill") and kind != "head" else MUTED if kind == "head" else INK
            page.insert_text((margin + 6 + x, y), text, fontsize=8.5 if kind == "head" else 9.5,
                             fontname="hebo" if kind == "head" else "helv", color=colour)
        page.draw_line((margin, y + 5), (W - margin, y + 5), color=(0.9, 0.9, 0.92), width=0.4)
        y += line_h + 2

    y += 14
    if y < H - margin:
        x = margin
        for colour, text in ((FILL, "fill"), (CUT, "cut"), (GROUND, "existing ground"),
                             (DESIGN, "proposed surface"), (EDITED, "edited by hand")):
            page.draw_rect(fitz.Rect(x, y - 7, x + 9, y + 2), color=None, fill=colour)
            page.insert_text((x + 13, y), text, fontsize=8.5, fontname="helv", color=MUTED)
            x += 30 + fitz.get_text_length(text, fontname="helv", fontsize=8.5)


def annotated_pdf(src_path: str, geometries: list[dict | None], payload: dict, surface: str,
                  excluded: set[str]) -> bytes:
    """`geometries[i]` is section i's page geometry (SectionResult.geometry);
    `payload` the API result with the current (possibly edited) areas and
    volumes."""
    doc = fitz.open(src_path)
    edits = payload["edits"].get(surface, {})
    for sec, geom in zip(payload["sections"], geometries):
        if not geom or not 1 <= sec["page"] <= len(doc):
            continue
        page = doc[sec["page"] - 1]
        _shade(page, geom, surface if geom.get(surface) else "finished")
        _label(page, geom, sec, surface, str(sec["id"]) in edits)

    roads = []
    tf = tc = 0.0
    for r in payload["roads"]:
        v = r["volumes"][surface]
        counted = r["id"] not in excluded
        if counted:
            tf, tc = tf + v["fill_cy"], tc + v["cut_cy"]
        roads.append({"label": r["label"], "from": r["station_from"], "to": r["station_to"],
                      "sections": len(r["sections"]), "counted": counted, "repeat": bool(r["repeat_of"]),
                      "fill_cy": v["fill_cy"], "cut_cy": v["cut_cy"], "net_cy": v["net_cy"]})
    secs = payload["sections"]
    summary = {
        "totals": {"fill_cy": tf, "cut_cy": tc, "net_cy": tf - tc},
        "sections": len(secs),
        "roads": roads,
        "counted": sum(r["counted"] for r in roads),
        "surface_label": "subgrade (bottom of pavement)" if surface == "subgrade" else "finished grade",
        "edits": [{"station": secs[int(i)]["station"], "page": secs[int(i)]["page"],
                   "fill": a["fill_ft2"], "cut": a["cut_ft2"],
                   "m_fill": secs[int(i)]["measured"][surface]["fill_ft2"],
                   "m_cut": secs[int(i)]["measured"][surface]["cut_ft2"]}
                  for i, a in sorted(edits.items(), key=lambda kv: int(kv[0]))],
    }
    _summary_pages(doc, payload["filename"], summary)
    out = doc.tobytes(deflate=True, garbage=1)
    doc.close()
    return out
