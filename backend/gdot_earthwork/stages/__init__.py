"""
The pipeline as independent stages, run in this order for every page and
then once over the whole document:

  ingest     open a page as an image (scan or rendered vector), with its text
             and vector strokes                              -> stages.ingest
  detect     find every cross-section frame on it and read its station label
             (turning sideways sheets upright)               -> stages.detect
  calibrate  feet per grid square on each axis, from the axis labels, and the
             centreline (offset 0)                           -> stages.calibrate
  trace      trace existing ground and the proposed surfaces -> stages.trace
  measure    fill / cut areas (whole, per 1 ft strip, left / right), why a
             section has none, and what to warn about       -> stages.measure
  decode     decode the station sequence across the document (repairing
             misread labels)                                 -> stages.decode

Each stage takes plain inputs and returns plain results, so any one can be
run, tested or replaced on its own; plan_set.process_plan_set chains them.
The algorithms themselves live in pages, frames, surfaces, tracing and
stations -- the stages are their entry points.
"""
from .calibrate import FrameScale, calibrate
from .decode import decode_stations
from .detect import detect
from .ingest import ingest
from .measure import SectionMeasure, measure_section
from .trace import trace

__all__ = ["ingest", "detect", "calibrate", "FrameScale", "trace", "measure_section", "SectionMeasure",
           "decode_stations"]
