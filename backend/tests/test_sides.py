"""
Left / right of the centreline: the centreline is read off each section's
offset axis (text layer, or OCR on a scan), and the measured areas split
there match the exact geometry on both sides.
"""
import pytest

from gdot_earthwork import process_plan_set
from gdot_earthwork.sides import current_sides, polygon_sides, split_strips

from .synth import cut_section, embankment, make_pdf, rolling_section, true_side_areas

SPECS = [[embankment("30+00", 700.0, 6.0, tilt=0.02), rolling_section("30+50", 701.0, amp=2.2, phase=35.0)],
         [cut_section("31+00", 705.0, 6.0)]]
BY_STATION = {s.station: s for page in SPECS for s in page}


@pytest.mark.parametrize("scanned, source, tol_rel, tol_abs", [(False, "text", 0.02, 3.0), (True, "scan", 0.05, 5.0)])
def test_left_and_right_areas_match_the_geometry(tmp_path, scanned, source, tol_rel, tol_abs):
    path = tmp_path / "sides.pdf"
    make_pdf(str(path), SPECS, scanned=scanned)
    result = process_plan_set(str(path), workers=1, overlays=False)
    assert sorted(s.station_label for s in result.sections) == ["30+00", "30+50", "31+00"]
    for s in result.sections:
        assert s.centre_source == source, s.station_label
        assert s.centre_ft == pytest.approx(140.0, abs=0.5)        # the grid runs -140 ... 140
        true = true_side_areas(BY_STATION[s.station_label])
        got = s.sides[result.design_surface]
        for side in ("left", "right"):
            for kind in ("fill_ft2", "cut_ft2"):
                assert got[side][kind] == pytest.approx(true[side][kind], rel=tol_rel, abs=tol_abs), \
                    (s.station_label, side, kind)
        # the two sides add up to the section's totals
        assert got["left"]["fill_ft2"] + got["right"]["fill_ft2"] == pytest.approx(s.fill_ft2, abs=0.05)
        assert got["left"]["cut_ft2"] + got["right"]["cut_ft2"] == pytest.approx(s.cut_ft2, abs=0.05)


def test_splitting_strips_and_outlines():
    assert split_strips([1, 2, 3, 4], 2.0) == (3.0, 7.0)
    assert split_strips([1, 2, 3, 4], 2.5) == (4.5, 5.5)           # a strip cut by the centreline
    assert polygon_sides([[0, 0], [10, 0], [10, 4], [0, 4]], 2.5) == (10.0, 30.0)


def test_edited_areas_keep_their_side():
    measured = {"left": {"fill_ft2": 30.0, "cut_ft2": 10.0}, "right": {"fill_ft2": 10.0, "cut_ft2": 0.0}}
    total = {"fill_ft2": 40.0, "cut_ft2": 10.0}
    # typing double the fill stretches both sides alike
    got = current_sides(measured, total, {"fill_ft2": 80.0, "cut_ft2": 10.0}, [])
    assert got["left"]["fill_ft2"] == 60.0 and got["right"]["fill_ft2"] == 20.0
    # an outlined fill on the right adds to the right only; removing left fill takes from the left only
    marks = [{"kind": "fill", "ft2": 5.0, "sides": {"left": 0.0, "right": 5.0}},
             {"kind": "remove_fill", "ft2": 12.0, "sides": {"left": 12.0, "right": 0.0}}]
    got = current_sides(measured, total, {"fill_ft2": 40.0 - 12.0 + 5.0, "cut_ft2": 10.0}, marks)
    assert got["left"]["fill_ft2"] == 18.0 and got["right"]["fill_ft2"] == 15.0
    assert got["left"]["cut_ft2"] == 10.0 and got["right"]["cut_ft2"] == 0.0
    # fill typed where nothing was traced cannot be put on a side
    got = current_sides(measured, {"fill_ft2": 40.0, "cut_ft2": 0.0}, {"fill_ft2": 40.0, "cut_ft2": 7.0},
                        [])
    assert got["unplaced"]["cut_ft2"] == 7.0
