"""Stage 2 -- detect: the cross-section frames on a page, with their stations."""
from __future__ import annotations

from ..config import PipelineConfig
from ..frames import Frame, find_frames, label_frames
from ..pages import PageImage, sideways_labels


def detect(img: PageImage, cfg: PipelineConfig) -> tuple[list[Frame], PageImage]:
    """Every gridded cross-section frame on the page and its station label.
    A frame only counts when a station is found in it (that is the page
    classification). Sheets plotted sideways are turned upright first; the
    image the frames refer to is returned with them."""
    frames = label_frames(find_frames(img, cfg.ink_thresh), img, cfg.ink_thresh)
    # read like a scan when there is no text layer to tell which way is up
    rotated_plot = img.kind == "raster" or not img.spans or sideways_labels(img.page)
    if rotated_plot and not any(f.station_label for f in frames):
        # nothing readable upright: the sections may be plotted sideways
        for k in (-1, 1):
            turned = img.rotated(k)
            alt = label_frames(find_frames(turned, cfg.ink_thresh), turned, cfg.ink_thresh)
            if sum(f.station_label is not None for f in alt) > sum(f.station_label is not None for f in frames):
                frames, img = alt, turned
    return frames, img
