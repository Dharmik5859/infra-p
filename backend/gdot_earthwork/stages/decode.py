"""Stage 6 -- decode stations: the station sequence across the document."""
from __future__ import annotations

from ..stations import StationRead, repair


def decode_stations(sections: list) -> list[str]:
    """Decode every section's station along the document (sections in
    document order), repairing misread labels and placing unread ones from
    the sequence; updates the sections in place. Returns document-level
    warnings."""
    reads = repair([StationRead(s.station_label, s.station_ft, s.label_confidence, s.label_source,
                                candidates=s.label_candidates) for s in sections])
    for s, r in zip(sections, reads):
        if r.source == "inferred":
            s.station_label, s.station_ft, s.label_source = r.label, r.station_ft, "inferred"
            s.warnings.append(r.note)
        elif r.label != s.station_label:      # an alternative OCR reading was chosen
            s.station_label, s.station_ft, s.label_confidence = r.label, r.station_ft, r.confidence
    unlabelled = [s for s in sections if s.station_ft is None]
    if not unlabelled:
        return []
    return [f"{len(unlabelled)} cross-section(s) had no readable station and could not be placed along a road: "
            + ", ".join(f"page {s.page}" for s in unlabelled[:10])]
