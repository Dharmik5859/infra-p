"""stages.calibrate: feet per grid square on each axis, read off the axis
labels, and areas measured with it -- on sheets drawn at known scales, as
vector PDFs and as scans."""
import pytest

from gdot_earthwork.plan_set import process_plan_set
from gdot_earthwork.stages.calibrate import fit_elevation_step, fit_offset_step

from .synth import Grid, cut_section, embankment, make_pdf, true_areas

GRIDS = {
    "10 x 10 ft": Grid(),
    "10 ft across, 5 ft up (2x vertical)": Grid(ft_x=10, ft_y=5, pt_x=3.6, pt_y=7.2),
    "20 x 20 ft (1 in = 40 ft)": Grid(ft_x=20, ft_y=20, pt_x=1.8, pt_y=1.8),
    "20 ft across, 5 ft up": Grid(ft_x=20, ft_y=5, pt_x=1.8, pt_y=7.2),
}


@pytest.mark.parametrize("scanned", [False, True], ids=["vector", "scan"])
@pytest.mark.parametrize("name", list(GRIDS))
def test_scale_read_per_axis_and_areas_follow(tmp_path, name, scanned):
    g = GRIDS[name]
    specs = [embankment("11+50", 651.3, 5.0), cut_section("11+00", 655.0, 4.0)]
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [specs], scanned=scanned, grid=g)
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    assert len(res.sections) == 2
    for s in res.sections:
        assert s.scale["ftPerSquareX"] == g.ft_x and s.scale["ftPerSquareY"] == g.ft_y, s.scale
        assert s.scale["sourceX"] != "assumed" and s.scale["sourceY"] != "assumed"
        assert s.scale["verticalDiffers"] == (g.ft_x != g.ft_y)
        # pixels per ft follow the drawing: points per ft x the page image's pixels per point
        assert abs(s.px_per_ft[0] / s.px_per_ft[1] - g.pt_x / g.pt_y) < 0.03 * g.pt_x / g.pt_y
    by_station = {s.station_ft: s for s in res.sections if s.station_ft is not None}
    for spec in specs:
        ft = int(spec.station.split("+")[0]) * 100 + int(spec.station.split("+")[1])
        if ft not in by_station:          # a scan's station OCR can miss; the scale is what is tested here
            continue
        s = by_station[ft]
        fill, cut = true_areas(spec)
        assert abs(s.alt_fill_ft2 - fill) <= max(3.0, 0.03 * fill), (s.alt_fill_ft2, fill)
        assert abs(s.alt_cut_ft2 - cut) <= max(3.0, 0.03 * cut), (s.alt_cut_ft2, cut)


def test_offset_step_fit():
    lines = 29
    # 10 ft squares, signed labels every line, offset 0 at line 14
    assert fit_offset_step([(k, (k - 14) * 10) for k in range(0, 29, 3)], lines, True) == (10.0, 10)
    # 20 ft squares, unsigned left side
    assert fit_offset_step([(k, abs(k - 7) * 20) for k in range(0, 15)], 15, False)[0] == 20.0
    # a misread among many still gives the step; too few labels give nothing
    reads = [(k, (k - 14) * 10) for k in range(4, 24)] + [(25, 190)]
    assert fit_offset_step(reads, lines, True)[0] == 10.0
    assert fit_offset_step([(3, -110), (4, -100)], lines, True) is None


def test_elevation_step_fit():
    assert fit_elevation_step([(0, 1090.0), (1, 1080.0), (2, 1070.0), (3, 1060.0)]) == (10.0, 4)
    assert fit_elevation_step([(0, 660.0), (1, 655.0), (2, 650.0), (4, 640.0)]) == (5.0, 4)
    assert fit_elevation_step([(0, 660.0), (1, 655.0)]) is None
