"""
Sections with several separate cut and fill zones (rolling ground crossing
the template more than once): every zone must be counted, on vector and
scanned sheets alike.
"""
import pytest

from gdot_earthwork import process_plan_set

from .synth import make_pdf, rolling_section, true_areas, zones

SPECS = [[rolling_section("20+50", 702.0, amp=2.0, phase=0.0),
          rolling_section("20+00", 701.5, amp=2.5, phase=20.0)],
         [rolling_section("21+00", 702.4, amp=1.6, phase=40.0)]]
BY_STATION = {s.station: s for page in SPECS for s in page}


def test_synthetic_sections_really_are_mixed():
    for spec in BY_STATION.values():
        n_fill, n_cut = zones(spec)
        assert n_fill >= 2 and n_cut >= 2, (spec.station, n_fill, n_cut)


@pytest.mark.parametrize("scanned, tol_rel, tol_abs", [(False, 0.02, 3.0), (True, 0.05, 5.0)])
def test_every_cut_and_fill_zone_is_counted(tmp_path, scanned, tol_rel, tol_abs):
    path = tmp_path / "mixed.pdf"
    make_pdf(str(path), SPECS, scanned=scanned)
    result = process_plan_set(str(path), workers=1, overlays=False)
    assert sorted(s.station_label for s in result.sections) == ["20+00", "20+50", "21+00"]
    for s in result.sections:
        fill, cut = true_areas(BY_STATION[s.station_label])
        assert s.fill_ft2 == pytest.approx(fill, rel=tol_rel, abs=tol_abs), (s.station_label, "fill")
        assert s.cut_ft2 == pytest.approx(cut, rel=tol_rel, abs=tol_abs), (s.station_label, "cut")
