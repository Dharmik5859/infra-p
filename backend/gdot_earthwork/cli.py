"""
Command-line entry point.

    python -m gdot_earthwork.cli plans.pdf [--out results/] [--no-overlays]

Prints a per-road volume table and writes sections.csv, volumes.csv and
one overlay PNG per cross-section into --out.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

from .plan_set import process_plan_set


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Earthwork cut/fill volumes from a cross-section plan set")
    ap.add_argument("pdf")
    ap.add_argument("--out", default="earthwork_out")
    ap.add_argument("--no-overlays", action="store_true")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)

    def progress(done, total):
        print(f"\r  pages {done}/{total}", end="", file=sys.stderr, flush=True)

    res = process_plan_set(args.pdf, workers=args.workers, overlays=not args.no_overlays, progress=progress)
    print(file=sys.stderr)
    os.makedirs(args.out, exist_ok=True)

    with open(os.path.join(args.out, "sections.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["page", "station", "station_source", "fill_ft2", "cut_ft2", "method", "warnings"])
        for i, s in enumerate(res.sections):
            w.writerow([s.page, s.station_label, s.label_source, s.fill_ft2, s.cut_ft2, s.method, " | ".join(s.warnings)])
            if s.overlay_png:
                name = f"p{s.page:03d}_{(s.station_label or f'section{i}').replace('+', '_')}.png"
                with open(os.path.join(args.out, name), "wb") as img:
                    img.write(s.overlay_png)

    with open(os.path.join(args.out, "volumes.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["road", "from", "to", "length_ft", "fill_cy", "cut_cy", "net_cy", "note"])
        for road, vol in zip(res.roads, res.volumes):
            for s in vol.segments:
                w.writerow([road.label, s.station_from, s.station_to, s.length_ft, s.fill_cy, s.cut_cy, s.net_cy, s.warning or ""])

    print(f"{res.pages} pages, {res.cross_section_pages} with cross-sections, {len(res.sections)} sections, "
          f"{res.timing['total_seconds']}s")
    for road, vol in zip(res.roads, res.volumes):
        tag = f"  (repeat of {road.repeat_of})" if road.repeat_of else ""
        print(f"  {road.label:8s} {road.entries[0].station_label:>10} -> {road.entries[-1].station_label:<10} "
              f"fill {vol.total_fill_cy:10.1f} cy   cut {vol.total_cut_cy:10.1f} cy   net {vol.total_net_cy:+10.1f} cy{tag}")
    for w_ in res.warnings:
        print("WARNING:", w_)
    print(f"results written to {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
