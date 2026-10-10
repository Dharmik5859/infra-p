"""
Repair station labels across a whole plan set.

Text-layer labels are exact. OCR'd labels on scans are usually right but
not always: a thin italic "1" gets dropped ("4+50" for "14+50"), a "+" is
read as "4+" ("914+50" for "91+50"), or nothing is read at all. A road's
cross-sections are drawn at a regular step (50 ft, 100 ft, ...) and in
order, so the sequence itself tells which reading is right.

The labels are decoded jointly (Viterbi): every section offers its OCR
readings plus an "infer it" option; a reading scores by its OCR votes, and
each consecutive pair scores by whether it steps forward by the road's
regular step. Going backwards or jumping far is allowed -- that is a road
change -- but costs points, so a lone misread loses to the reading (or the
inference) that keeps the sequence regular. Inferred labels are marked and
reported, never silently trusted.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .pages import parse_station


@dataclass
class StationRead:
    label: str | None
    station_ft: float | None
    confidence: float          # 1.0 = text layer or two OCR reads agreeing
    source: str | None         # "text" | "ocr" | "inferred" | None
    note: str | None = None
    candidates: tuple[str, ...] = ()   # alternative OCR readings


def format_station(ft: float, decimals: int = 0) -> str:
    whole = int(ft // 100)
    rest = ft - whole * 100
    return f"{whole}+{rest:0{3 + decimals if decimals else 2}.{decimals}f}"


def _typical_step(reads: list[StationRead]) -> float | None:
    """The road's usual station step, from confidently read labels (or all
    labels when few are confident). Uncertain reads often alternate with good
    ones, so steps are measured between successive reads and divided by the
    number of sections apart."""
    good = [(i, r.station_ft) for i, r in enumerate(reads)
            if r.confidence >= 1.0 and r.station_ft is not None]
    if len(good) < 3:
        good = [(i, r.station_ft) for i, r in enumerate(reads) if r.station_ft is not None]
    diffs = [round((b - a) / (j - i), 2) for (i, a), (j, b) in zip(good, good[1:]) if b > a]
    if not diffs:
        return None
    # most frequent step; on a tie the smaller one (a misread makes an
    # absurdly large jump, never a small one)
    return max(Counter(diffs).items(), key=lambda kv: (kv[1], -kv[0]))[0]


INFER = None          # the "infer this label" option
_INFER_COST = -1.5
_REGULAR, _NEAR, _BREAK = 3.0, 1.5, -2.0


def _options(r: StationRead) -> list[tuple[float | None, str | None, float]]:
    """(station_ft, label, emission score) choices for one section."""
    if r.source == "text":
        return [(r.station_ft, r.label, 0.0)]
    opts: dict[float, tuple[float, str, float]] = {}
    if r.station_ft is not None:
        opts[r.station_ft] = (r.station_ft, r.label, 1.0 if r.confidence >= 1.0 else 0.5)
    for c in r.candidates:
        ft = parse_station(c)
        if ft is not None and ft not in opts:
            opts[ft] = (ft, c, 0.3)
    return list(opts.values()) + [(INFER, None, _INFER_COST)]


def _transition(a: float, b: float, expected: float, step: float) -> float:
    d = b - a
    if abs(d - expected) <= 0.5:
        return _REGULAR
    if 0 < d <= expected + step + 0.5:
        return _NEAR                 # an inserted station (26+40) or a missing section
    return _BREAK                    # road change, or a misread


def repair(reads: list[StationRead]) -> list[StationRead]:
    """`reads` must be in document order with each road ascending."""
    step = _typical_step(reads)
    if not step or not reads:
        return reads
    opts = [_options(r) for r in reads]

    # Viterbi over the options of each section. An "infer" option carries no
    # value of its own, so the next real reading is scored against the last
    # real one, expecting one step per section in between -- an inferred gap
    # can't hide a backwards jump around it.
    score = [o[2] for o in opts[0]]
    last = [(o[0], 0) for o in opts[0]]          # (last real station, sections since)
    back: list[list[int]] = [[-1] * len(opts[0])]
    for i in range(1, len(reads)):
        row, row_last, ptr = [], [], []
        for ft, _, em in opts[i]:
            best, arg, best_last = float("-inf"), 0, (None, 0)
            for k in range(len(opts[i - 1])):
                ref, since = last[k]
                s = score[k]
                if ft is not None and ref is not None:
                    s += _transition(ref, ft, step * (since + 1), step)
                if s > best:
                    best, arg = s, k
                    best_last = (ft, 0) if ft is not None else (ref, since + 1)
            row.append(best + em)
            row_last.append(best_last)
            ptr.append(arg)
        score, last = row, row_last
        back.append(ptr)
    k = max(range(len(score)), key=lambda j: score[j])
    choice = [0] * len(reads)
    for i in range(len(reads) - 1, -1, -1):
        choice[i] = k
        k = back[i][k]

    decimals = 2 if any(r.label and "." in r.label for r in reads) else 0
    out: list[StationRead] = []
    for r, o, c in zip(reads, opts, choice):
        ft, label, _ = o[c]
        if ft is None:
            out.append(StationRead(None, None, 0.0, None, None, r.candidates))
        elif label == r.label:
            out.append(r)
        else:                                    # an alternative OCR reading fitted better
            out.append(StationRead(label, ft, 0.9, "ocr", None, r.candidates))
    _fill_inferred(out, reads, step, decimals)
    return out


def _fill_inferred(out: list[StationRead], reads: list[StationRead], step: float, decimals: int) -> None:
    """Give every section decoded as "infer" a station from its neighbours."""
    n = len(out)
    i = 0
    while i < n:
        if out[i].station_ft is not None:
            i += 1
            continue
        j = i
        while j < n and out[j].station_ft is None:
            j += 1                                           # out[i:j] need values
        prev = out[i - 1].station_ft if i > 0 else None
        nxt = out[j].station_ft if j < n else None
        for k in range(i, j):
            if prev is not None:
                ft = prev + (k - i + 1) * step
            elif nxt is not None:
                ft = nxt - (j - k) * step
            else:
                continue
            if ft < 0 or (nxt is not None and prev is not None and ft >= nxt):
                continue                                     # neighbours don't leave room: leave unplaced
            label = format_station(ft, decimals)
            was = reads[k].label or "unreadable"
            out[k] = StationRead(label, ft, 0.5, "inferred",
                                 f"station read as {was!r}; inferred {label} from the "
                                 f"{step:g} ft station sequence", reads[k].candidates)
        i = j
