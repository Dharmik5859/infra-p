"""
Confidence per cross-section: how far its numbers can be trusted without a
look, on a 0-100 scale. Sections at PASS_SCORE or above pass; below it the
section carries alerts saying what to check.

The score starts at 100 and loses points for each thing the pipeline had to
guess or work around -- every deduction is listed, so the score explains
itself:

  station     read from the text layer (0), by OCR (by its confidence),
              inferred from the neighbours, or not placed at all
  scale       ft per grid square read off the axis labels (0) or assumed
  centreline  read off the offset axis (0), borrowed from a neighbour, or
              assumed at the middle of the grid (left / right split)
  tracing     CAD linework (0) or a scan; surfaces bridged across gaps,
              buried runs trimmed, structures spanned
  no earthwork  a 0 / 0 section with no design line drawn
  jump        an area several times both neighbours' on the same road
              (a mistraced line usually shows as one)
"""
from __future__ import annotations

PASS_SCORE = 85


def _deductions(s, prev=None, nxt=None) -> list[dict]:
    out: list[dict] = []

    def take(factor: str, points: float, note: str) -> None:
        if points > 0:
            out.append({"factor": factor, "points": round(points, 1), "note": note})

    src = s.label_source
    if s.station_ft is None:
        take("station", 35, "no station could be read or inferred -- the section is not in any road's volumes")
    elif src == "inferred":
        take("station", 20, "station inferred from the neighbouring sections, not read")
    elif src == "ocr":
        take("station", min(15.0, 25 * (1 - (s.label_confidence or 0))),
             f"station read by OCR ({(s.label_confidence or 0) * 100:.0f}% agreement)")

    scale = s.scale or {}
    if scale.get("sourceX") == "assumed":
        take("scale", 5 if s.page_kind == "vector" else 3,
             f"horizontal scale assumed at {scale.get('ftPerSquareX', 10):g} ft per grid square -- axis labels not read")
    if scale.get("verticalDiffers"):
        take("scale", 2, f"vertical scale {scale.get('ftPerSquareY'):g} ft per square differs from the horizontal "
                         f"{scale.get('ftPerSquareX'):g} -- check the sheet's scale note")

    if s.centre_source == "neighbour":
        take("centreline", 5, "centreline taken from the neighbouring section")
    elif s.centre_source == "assumed":
        take("centreline", 10, "centreline assumed at the middle of the grid -- left / right split uncertain")

    if s.method == "raster":
        take("tracing", 5, "traced from a scan, not CAD linework")
    w = " ".join(s.warnings or [])
    if "bridged across" in w:
        take("tracing", 10, "a surface was bridged across a gap with no ink")
    n_trim = w.count("buried pipe")
    if n_trim:
        take("tracing", min(10, 5 * n_trim), "buried runs below ground were left out")
    if "marks a bridge here" in w:
        take("tracing", 20, "the drawing marks a bridge: the space under the deck is counted as fill")
    if "bridge deck or structure" in w:
        take("tracing", 5, "a structure spans part of the section")

    if s.zero_reason == "no_design":
        take("no earthwork", 15, "no proposed surface was found -- 0 cut / 0 fill")
    elif s.zero_reason == "matches_existing":
        take("no earthwork", 5, "proposed surface follows existing ground -- 0 cut / 0 fill")

    total = s.fill_ft2 + s.cut_ft2
    near = [o.fill_ft2 + o.cut_ft2 for o in (prev, nxt) if o is not None]
    if len(near) == 2 and total > 200 and all(total > 4 * max(v, 1.0) for v in near):
        take("jump", 15, f"area {total:,.0f} ft² is over 4x both neighbours' ({near[0]:,.0f} and {near[1]:,.0f} ft²)")
    elif len(near) == 2 and all(v > 200 for v in near) and all(total * 4 < v for v in near):
        take("jump", 15, f"area {total:,.0f} ft² is under a quarter of both neighbours' "
                         f"({near[0]:,.0f} and {near[1]:,.0f} ft²)")
    return out


def score(s, prev=None, nxt=None) -> dict:
    """{score, passed, deductions, alerts} for a section (plan_set.SectionResult);
    prev / nxt: its neighbours on the same road, for the jump check."""
    ded = _deductions(s, prev, nxt)
    value = max(0, round(100 - sum(d["points"] for d in ded)))
    passed = value >= PASS_SCORE
    alerts = [] if passed else [{
        "level": "warning" if value >= 60 else "error",
        "message": f"Low confidence ({value}%): check this section before using its numbers.",
        "reasons": [d["note"] for d in sorted(ded, key=lambda d: -d["points"])],
    }]
    return {"score": value, "passed": passed, "threshold": PASS_SCORE, "deductions": ded, "alerts": alerts}


def score_sections(sections: list, roads: list) -> None:
    """Score every section in place (s.confidence); neighbours are taken along
    each road, sections on no road are scored alone."""
    done = set()
    for r in roads:
        refs = [e.ref for e in r.entries]
        for i, s in enumerate(refs):
            s.confidence = score(s, refs[i - 1] if i > 0 else None, refs[i + 1] if i + 1 < len(refs) else None)
            done.add(id(s))
    for s in sections:
        if id(s) not in done:
            s.confidence = score(s)
