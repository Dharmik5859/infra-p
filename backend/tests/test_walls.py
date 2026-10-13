"""Deep cuts retained by a wall: the template ends at the wall's foot, deep
below ground, which must neither be taken for a buried pipe nor lose the
back slope above the wall."""
import numpy as np
import pytest

from gdot_earthwork.plan_set import process_plan_set
from gdot_earthwork.tracing import trim_buried_tail

from .synth import Grid, make_pdf, true_areas, true_side_areas, walled_cut


@pytest.mark.parametrize("scanned", [False, True], ids=["vector", "scan"])
def test_walled_cut_is_measured_whole(tmp_path, scanned):
    specs = [walled_cut("20+50", 640, 28.0), walled_cut("20+00", 640, 36.0)]
    pdf = tmp_path / "wall.pdf"
    make_pdf(str(pdf), [specs], scanned=scanned, grid=Grid(pt_x=2.4, pt_y=2.4), squares=6)
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    assert len(res.sections) == 2
    # sheets stack the higher station on top; the document is read ascending
    for s, spec in zip(res.sections, specs[::-1]):
        fill, cut = true_areas(spec)
        assert abs(s.cut_ft2 - cut) <= 0.02 * cut, (s.station_label, s.cut_ft2, cut)
        assert not any("buried pipe" in w for w in s.warnings)
        left = true_side_areas(spec)["left"]["cut_ft2"]
        assert abs(s.sides["subgrade"]["left"]["cut_ft2"] - left) <= 0.03 * left


def test_buried_service_still_trimmed_but_not_the_roadway():
    ppf = 14.4
    x = (np.arange(4000) - 2000) / ppf
    ground = np.full(4000, 500.0)
    # a template tied to ground on the left, with a 6 ft deep pipe running on
    # from the toe at +40 ft to the edge of the frame
    design = np.full(4000, np.nan)
    design[1400:2576] = 500.0 - 0.0                  # on the ground: no cut
    design[2576:] = 500.0 + 6 * ppf                    # the pipe, 6 ft below ground
    _, killed = trim_buried_tail(x, ground, design, ppf, 25.0, 3.5)
    assert killed and killed[0]["side"] == "right"
    # a pipe crossing under the road a few feet down is still a pipe ...
    design2 = np.full(4000, np.nan)
    design2[1400:] = 500.0 + 6 * ppf
    design2[1400:1420] = 500.0
    _, killed = trim_buried_tail(x, ground, design2, ppf, 25.0, 3.5)
    assert killed
    # ... but a run 20 ft down under the middle is the roadway in a deep cut
    design2[1420:] = 500.0 + 20 * ppf
    _, killed = trim_buried_tail(x, ground, design2, ppf, 25.0, 3.5)
    assert not killed


def test_new_road_built_down_through_the_old_one_is_cut_not_a_pipe():
    """The proposed pavement 4 ft under the existing road, up to where the
    drawing stops: the old asphalt and earth above it are dug out (cut). A
    single line at the same place is still read as a pipe."""
    ppf = 14.4
    x = (np.arange(4000) - 2000) / ppf
    ground = np.full(4000, 500.0)
    surface = np.full(4000, np.nan)
    surface[1400:3100] = 500.0 + 4.0 * ppf             # catch at ground, then below it to the end
    surface[1400:1450] = 500.0 + np.linspace(0, 4.0 * ppf, 50)
    box = surface + 1.5 * ppf                          # subgrade: a pavement box under it
    _, killed = trim_buried_tail(x, ground, surface, ppf, 25.0, 3.5, subgrade=box)
    assert not killed
    _, killed = trim_buried_tail(x, ground, surface, ppf, 25.0, 3.5, subgrade=surface.copy())
    assert killed
