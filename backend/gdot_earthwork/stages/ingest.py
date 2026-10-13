"""Stage 1 -- ingest: one page of the PDF as an image to work on."""
from __future__ import annotations

import pymupdf as fitz

from ..config import PipelineConfig
from ..pages import PageImage, could_hold_sections, load_page


def ingest(doc: fitz.Document, index: int, cfg: PipelineConfig) -> PageImage | None:
    """The page (0-based `index`) as a PageImage: the scan at its own
    resolution, or a vector page rendered at cfg.vector_dpi, with its text
    spans and strokes. None for pages that cannot hold cross-sections
    (cover, plan and profile sheets ruled out cheaply)."""
    if not could_hold_sections(doc, index):
        return None
    return load_page(doc, index, cfg.vector_dpi)
