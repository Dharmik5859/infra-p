"""
The street a cross-section sheet shows, read from its title block.

GDOT sheets print the road's name in the title block (bottom right), on the
line under "CROSS SECTIONS":

    CROSS SECTIONS                       CROSS SECTIONS
    FRANKLIN GATEWAY OVER ROTTENWOOD CREEK   NEW HOPE RD AT WYLIE RD INTERSECTION
                                         NEW HOPE RD (WEST APPROACH)

The name is the first line below that looks like a road ("SR 136", "CR 29/
MARTINS MILL RD", "MOUNTAIN INDUSTRIAL BLVD"); a line naming only the road
(no "AT", "@", "OVER", "IMPROVEMENTS") is preferred, and what follows "AT" /
"@" / "OVER" (the crossing, the project) is cut off. The text layer is read
where there is one, the title block is OCR'd on scans. Failing both, the
file name ("RIVER SIDE ROAD - MAINLINE.pdf") is used.

    sheet_street(img)          the street on one sheet, or None
    street_from_name(name)     the street in a file name, or None
    name_roads(roads, ...)     label each road with its sections' street
"""
from __future__ import annotations

import re
from collections import Counter

from .pages import PageImage
from .staging import _ocr_words

_ROUTE = r"(?:S\.?\s?R\.?|U\.?\s?S\.?|C\.?\s?R\.?|I|HWY|HIGHWAY|ROUTE|RT)[ -]?\d+[A-Z]?"
_KIND = (r"RD|ROAD|DR|DRIVE|ST|STREET|WAY|BLVD|BOULEVARD|AVE|AVENUE|LN|LANE|PKWY|PARKWAY|HWY|HIGHWAY|"
         r"CONNECTOR|TRAIL|TRL|GATEWAY|MEMORIAL|PIKE|CIRCLE|CIR|CT|COURT|PL|PLACE|BYPASS|TER|TERRACE|LOOP|"
         r"EXPY|EXPRESSWAY|FWY|FREEWAY|CROSSING|XING|RUN|PATH|ROW|SQUARE|SQ|ALLEY|SPUR")
_ROAD_RE = re.compile(rf"\b{_ROUTE}\b|\b(?:{_KIND})\b\.?", re.I)
_NOT_A_NAME = re.compile(r"SCALE|FEET|DATE|REVISION|DEPARTMENT|DRAWING|SHEET|CHECKED|GPLOT|\.DGN|\.TBL|"
                         r"CROSS SECTION|SECTIONS|MATCH|EXIST|R/W|STA\.?\s*\d|\d+\+\d", re.I)
_PROJECT = re.compile(r"\s(?:AT|@|OVER|&|AND)\s|IMPROVEMENT|INTERSECTION|REPLACEMENT|WIDENING|PROJECT", re.I)
_CUT = re.compile(r"\s+(?:AT|@|OVER)\s+.*$", re.I)
_TAIL = re.compile(r"(?:\s+(?:CORRIDOR|IMPROVEMENTS?|WIDENING|RECONSTRUCTION|REPLACEMENT|PROJECT|PHASE\s*\w+))+$", re.I)
_KEEP_UPPER = re.compile(r"^(?:SR|US|CR|I|[A-Z]\.[A-Z]\.?)$|\d", re.I)


def _clean(line: str) -> str | None:
    """A title-block line as a street name, or None if it is not one."""
    line = re.sub(r"\s+", " ", line).strip(" |-_:;,")
    line = re.sub(r"^[A-Z]{1,4}\d?\s*:\s*", "", line)            # "DE2: SR 332"
    line = _CUT.sub("", line).strip(" |-_:;,")
    line = _TAIL.sub("", line).strip(" |-_:;,")
    words = line.split()
    while words and re.fullmatch(r"[^A-Za-z0-9]*[A-Za-z]?[^A-Za-z0-9]*", words[0]):
        words.pop(0)                                             # OCR specks: "—P—", "|", "."
    line = " ".join(words)
    if re.fullmatch(rf"(?:{_KIND})\.?", line, re.I):               # "Avenue" alone
        return None
    if re.match(r"^\d+\s+[A-Za-z]", line):                         # "2450 Commerce Avenue": an address
        return None
    if not line or len(line) > 60 or _NOT_A_NAME.search(line) or not _ROAD_RE.search(line):
        return None
    if sum(c.isalpha() for c in line) < 2 and not re.search(r"\d", line):
        return None
    return line


def pretty(name: str) -> str:
    """"CR 29/MARTINS MILL RD" -> "CR 29/Martins Mill Rd": words title-cased,
    route prefixes and numbers kept as printed."""
    def word(m: re.Match) -> str:
        w = m.group(0)
        return w if _KEEP_UPPER.search(w) else w.capitalize()
    return re.sub(r"[A-Za-z0-9.'\-]+", word, name)


def _lines(words: list[tuple[str, float, float, float, float]]) -> list[tuple[str, float, float, float]]:
    """Words (text, x, y, w, h) -> lines (text, x0, y, x1), top to bottom. A
    wide gap starts a new line, so blocks side by side stay apart."""
    rows: list[list] = []
    for w in sorted(words, key=lambda w: (w[2] + w[4] / 2, w[1])):
        t, x, y, ww, h = w
        cy = y + h / 2
        for row in rows:
            rh = max(o[4] for o in row)
            rcy = sum(o[2] + o[4] / 2 for o in row) / len(row)
            gap = max(min(o[1] for o in row) - (x + ww), x - max(o[1] + o[3] for o in row))
            if abs(cy - rcy) < 0.5 * max(h, rh) and gap < 2.5 * max(h, rh):
                row.append(w)
                break
        else:
            rows.append([w])
    out = []
    for row in rows:
        row.sort(key=lambda w: w[1])
        out.append((" ".join(w[0] for w in row), row[0][1], row[0][2] + row[0][4] / 2, row[-1][1] + row[-1][3]))
    out.sort(key=lambda r: r[2])
    return out


def street_from_lines(lines: list[tuple[str, float, float, float]]) -> str | None:
    """The street among title-block lines: below "CROSS SECTIONS" when that
    heading is there, the plain road name preferred to a project title."""
    heads = [i for i, (t, *_) in enumerate(lines) if re.search(r"CROSS\s*SECTION", t, re.I)]
    pool = lines[heads[0] + 1:heads[0] + 7] if heads else lines
    names = [(t, _clean(t)) for t, *_ in pool]
    names = [(raw, n) for raw, n in names if n]
    if not names:
        return None
    plain = [n for raw, n in names if not _PROJECT.search(raw)]
    return pretty(plain[0] if plain else names[0][1])


def sheet_street(img: PageImage) -> str | None:
    """The street printed in a sheet's title block (bottom right)."""
    H, W = img.gray.shape
    x0, y0 = int(W * 0.55), int(H * 0.78)
    if img.spans:
        words = []
        for sp in img.spans:
            if sp.x >= x0 and sp.y >= y0 and sp.text.strip():
                w = sp.w or 0.6 * sp.size * len(sp.text)
                h = sp.h or sp.size
                words.append((sp.text.strip(), sp.x - w / 2, sp.y - h / 2, w, h))
        found = street_from_lines(_lines(words))
        if found or len(words) > 5:
            return found
    words = _ocr_words(img.gray[y0:, x0:], 1.0 if max(H, W) < 9000 else 0.5)
    return street_from_lines(_lines([(t, x, y, w, h) for t, x, y, w, h in words]))


def street_from_name(name: str | None) -> str | None:
    """"RIVER SIDE ROAD - EARTHWORK MAINLINE.pdf" -> "River Side Road"."""
    if not name:
        return None
    stem = re.sub(r"\.pdf$", "", name.split("/")[-1], flags=re.I)
    for part in re.split(r"\s+-\s*|\s*-\s+|_", stem):
        n = _clean(re.sub(r"\b(?:CS|PLANS?|FULL PLAN|EARTHWORK|MAINLINE|CROSS SECTIONS?)\b", "", part, flags=re.I))
        if n:
            return pretty(n)
    return None


def name_roads(roads: list, fallback: str | None = None) -> None:
    """Label each road (roads.Road) with the street most of its sections'
    sheets name, else `fallback` (the file name's street). A street drawn as
    two runs of stations gets "(2)", "(3)"; roads with no name keep theirs."""
    seen: Counter = Counter()
    renamed = {}
    for r in roads:
        names = Counter(getattr(e.ref, "street", None) for e in r.entries)
        names.pop(None, None)
        street = names.most_common(1)[0][0] if names else fallback
        if not street:
            continue
        seen[street] += 1
        renamed[r.label] = street if seen[street] == 1 else f"{street} ({seen[street]})"
    for r in roads:                      # repeats point at the other road by its label
        if r.repeat_of in renamed:
            r.flags = [f.replace(f"repeat {r.repeat_of} --", f"repeat {renamed[r.repeat_of]} --") for f in r.flags]
            r.repeat_of = renamed[r.repeat_of]
    for r in roads:
        r.label = renamed.get(r.label, r.label)
