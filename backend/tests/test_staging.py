"""Staged-construction sheets: only the sheet's own stage is measured.
Stretches marked "STAGE n CONSTRUCTION" for another stage are left out; a
mark for the sheet's own stage, or a plan set that is not staged, changes
nothing."""
import numpy as np
import pytest

from gdot_earthwork.plan_set import process_plan_set
from gdot_earthwork.staging import other_stage, stage_from_name

from .synth import embankment, make_pdf


def _fill_left_of(spec, x_cut):
    x = np.linspace(-140, 140, 280001)
    d = np.interp(x, *zip(*spec.design), left=np.nan, right=np.nan) - np.interp(x, *zip(*spec.ground))
    keep = (x < x_cut) & ~np.isnan(d)
    return float(np.clip(d[keep], 0, None).sum() * (x[1] - x[0]))


@pytest.mark.parametrize("scanned", [False, True], ids=["vector", "scan"])
def test_other_stage_left_out_own_stage_kept(tmp_path, scanned):
    other = embankment("11+50", 651.3, 5.0)
    other.stage_mark = ("2", 5.0, 60.0)          # stage 2 work right of +5 ft
    own = embankment("11+00", 651.0, 4.0)
    own.stage_mark = ("3", 5.0, 60.0)            # this sheet's own stage: counted
    pdf = tmp_path / "ROAD - STAGE 3.pdf"
    make_pdf(str(pdf), [[other, own]], scanned=scanned, title="STAGE 3")
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    by_pos = {s.index: s for s in res.sections}
    s = by_pos[0]
    want = _fill_left_of(other, 5.0)
    assert abs(s.fill_ft2 - want) <= max(3.0, 0.03 * want), (s.fill_ft2, want)
    assert any("STAGE 2 CONSTRUCTION" in w for w in s.warnings)
    s = by_pos[1]
    full = _fill_left_of(own, 999)
    assert abs(s.fill_ft2 - full) <= 0.03 * full and not any("STAGE" in w for w in s.warnings)


def test_unstaged_plan_set_is_untouched(tmp_path):
    spec = embankment("11+50", 651.3, 5.0)
    pdf = tmp_path / "ROAD - MAINLINE.pdf"        # not a staged plan set: no stage logic at all
    make_pdf(str(pdf), [[spec]])
    s = process_plan_set(str(pdf), workers=1, overlays=False).sections[0]
    assert abs(s.fill_ft2 - _fill_left_of(spec, 999)) <= 0.03 * _fill_left_of(spec, 999)
    assert not any("STAGE" in w for w in s.warnings)


def test_stage_names():
    assert stage_from_name("RIVER SIDE ROAD - EARTHWORK -STAGE 3.pdf") == "3"
    assert stage_from_name("US 78 STAGE 1B.pdf") == "1B"
    assert stage_from_name("MAINLINE.pdf") is None
    assert other_stage("2", "3") and not other_stage("1", "1A") and not other_stage("1A", "1A")
    assert not other_stage(None, "3")


def test_other_stages_drawn_in_grey_are_left_out():
    """A staged sheet draws its own stage's work black and the other stages'
    grey: where a section has both, only the black template is measured.
    One pen only (or too little of either) changes nothing."""
    from gdot_earthwork.surfaces import CANON_PPF, own_pen
    W, H = int(200 * CANON_PPF), 300
    solid = np.zeros((H, W), np.uint8)
    gray = np.full((H, W), 255, np.uint8)
    own, other = slice(int(10 * CANON_PPF), int(60 * CANON_PPF)), slice(int(90 * CANON_PPF), int(150 * CANON_PPF))
    for cols, shade in ((own, 0), (other, 95)):
        solid[150:153, cols] = 1
        gray[150:153, cols] = shade
    kept, left_out = own_pen(solid, gray, W, H)
    assert kept[:, own].any() and not kept[:, other].any() and abs(left_out - 60) < 1
    gray[150:153, other] = 0                                 # all black: one pen
    kept, left_out = own_pen(solid, gray, W, H)
    assert (kept == solid).all() and left_out == 0
