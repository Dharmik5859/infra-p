"""Existing asphalt and utility poles in a section. The existing line is the
TOP of what is there: in cut, the asphalt is dug out with the earth (counted
as cut, measured from its top); in fill, it stays and the fill is built on
it (fill measured from its top, the asphalt itself never counted). Poles
are thin uprights and change nothing."""
import pytest

from gdot_earthwork.plan_set import process_plan_set

from .synth import cut_section, embankment, make_pdf, true_areas


def _with(spec, pavement, poles):
    spec.pavement, spec.poles = pavement, poles
    return spec


@pytest.mark.parametrize("scanned", [False, True], ids=["vector", "scan"])
def test_asphalt_and_poles_in_cut_and_fill(tmp_path, scanned):
    specs = [_with(embankment("11+50", 651.3, 5.0), [(-12, 12, 0.8)], [30, -60]),     # under fill
             _with(cut_section("11+00", 655.0, 4.0), [(-12, 12, 0.8)], [-20, 70])]    # in cut
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [specs], scanned=scanned)
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    assert len(res.sections) == 2
    for s in res.sections:
        spec = specs[s.index]            # position on the sheet, top to bottom (as drawn)
        fill, cut = true_areas(spec)
        assert abs(s.fill_ft2 - fill) <= max(3.0, 0.02 * fill), (spec.station, s.fill_ft2, fill)
        assert abs(s.cut_ft2 - cut) <= max(3.0, 0.02 * cut), (spec.station, s.cut_ft2, cut)
