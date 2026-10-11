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


@pytest.mark.parametrize("scanned", [False, True])
def test_resurfacing_section_reports_why_it_has_no_earthwork(tmp_path, scanned):
    from .synth import SectionSpec
    ground = [(-140.0, 700.0), (-30.0, 700.6), (0.0, 701.2), (30.0, 700.6), (140.0, 700.0)]
    on_ground = [(-30.0, 700.6), (0.0, 701.2), (30.0, 700.6)]          # new surface = existing
    specs = [[SectionSpec("30+50", ground, on_ground), rolling_section("30+00", 701.0)]]
    path = tmp_path / "resurface.pdf"
    make_pdf(str(path), specs, scanned=scanned)
    result = process_plan_set(str(path), workers=1, overlays=False)
    # identify by position on the sheet (top first), independent of OCR
    flat, rolling = sorted(result.sections, key=lambda s: s.index)
    assert flat.fill_ft2 + flat.cut_ft2 < 0.5
    assert flat.zero_reason in ("matches_existing", "no_design")
    assert rolling.zero_reason is None and rolling.fill_ft2 > 20
