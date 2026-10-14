"""
Group cross-sections into roads (alignments), in document order.

Two roads can share the same station step (a mainline at 100+00, 100+50,
... and a side road at 20+00, 20+50, ...), so stations can't simply be
sorted and split at gaps. The reliable signal is DOCUMENT ORDER: a plan
set lays out one road's cross-sections consecutively, in increasing
station order, before moving to the next. A new road starts when the
station drops or repeats, or jumps far beyond the road's usual step.

The same alignment is often drawn twice in one plan set (e.g. a grading
series and a separate staging series). From station numbers alone that
looks like a second road, so when a road's stations largely repeat an
earlier road's it is flagged as a likely repeat; callers decide whether to
count it (the API excludes repeats from the grand total by default).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StationEntry:
    station_label: str
    station_ft: float
    page: int
    ref: Any = None


@dataclass
class Road:
    label: str
    entries: list[StationEntry] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    repeat_of: str | None = None


def _step(road: Road) -> float | None:
    diffs = sorted(b.station_ft - a.station_ft
                   for a, b in zip(road.entries, road.entries[1:])
                   if b.station_ft > a.station_ft)
    return diffs[len(diffs) // 2] if diffs else None


def group_into_roads(entries: list[StationEntry], max_jump: float = 4.0,
                     min_step_ft: float = 10.0) -> list[Road]:
    if not entries:
        return []
    roads = [Road("Road 1", [entries[0]])]
    for prev, e in zip(entries, entries[1:]):
        cur = roads[-1]
        diff = e.station_ft - prev.station_ft
        step = _step(cur)
        if diff <= 0 or (step and diff > max_jump * max(step, min_step_ft)):
            roads.append(Road(f"Road {len(roads) + 1}", [e]))
            continue
        if step and diff > 1.5 * step:
            cur.flags.append(
                f"{diff:.0f} ft gap between {prev.station_label} and {e.station_label} "
                f"(usual step {step:.0f} ft) -- a section may be missing here.")
        cur.entries.append(e)
    _flag_repeats(roads)
    return roads


def _flag_repeats(roads: list[Road], threshold: float = 0.7) -> None:
    for i, road in enumerate(roads):
        mine = {round(e.station_ft, 1) for e in road.entries}
        for other in roads[:i]:
            theirs = {round(e.station_ft, 1) for e in other.entries}
            if not mine or not theirs:
                continue
            overlap = len(mine & theirs) / min(len(mine), len(theirs))
            if overlap >= threshold:
                road.repeat_of = other.label
                road.flags.append(
                    f"{overlap:.0%} of these stations repeat {other.label} -- most likely the "
                    f"same alignment drawn again in another sheet series (e.g. staging). "
                    f"Excluded from the grand total unless you include it.")
                break
