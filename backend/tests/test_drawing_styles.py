"""Drawing styles met on real plan sets that the tracer must not be fooled by."""
import numpy as np

from gdot_earthwork.pages import TextSpan
from gdot_earthwork.plan_set import process_plan_set
from gdot_earthwork.stations import StationRead, repair
from gdot_earthwork.surfaces import CANON_PPF, _dash_chains, _half_box, _is_landed_leader, _is_underline
from gdot_earthwork.tracing import template_strokes

from .synth import Grid, cut_section, embankment, make_pdf, true_areas

P = CANON_PPF


def test_ground_drawn_dash_by_dash(tmp_path):
    """No dashed line style at all: every dash of the ground is its own stroke
    (New Hope at Wylie). The dashes are recognised by lining up end to end."""
    specs = [embankment("11+50", 651.3, 5.0), cut_section("11+00", 655.0, 4.0)]
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [specs], grid=Grid(dash_by_dash=True))
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    assert len(res.sections) == 2
    for s in res.sections:
        fill, cut = true_areas(specs[s.index])
        assert s.method == "vector"
        assert abs(s.fill_ft2 - fill) <= max(3.0, 0.03 * fill) and abs(s.cut_ft2 - cut) <= max(3.0, 0.03 * cut)


def test_dash_chains_keep_lines_not_letters():
    pen = (0.72, (0.0, 0.0, 0.0))
    line = [(x, 100.0, x + 0.8 * P, 100.0 + 0.1 * P) + pen for x in np.arange(0, 20 * P, 1.2 * P)]
    letters = [(500 + 3 * i, 50.0, 500 + 3 * i + 4, 58.0) + pen for i in range(6)]        # a word of tiny strokes
    got = _dash_chains(line + letters)
    assert len(got) == len(line)


def test_underline_with_lettering_is_not_template():
    seg = (100.0, 200.0, 100 + 20 * P, 200.0)
    word = [(100 + 1.2 * P * i, 200 - 1.2 * P, 100 + 1.2 * P * i + P, 200 - 0.2 * P) for i in range(15)]
    assert _is_underline(seg, word)
    assert not _is_underline(seg, word[:3])          # a "2.0%" label over a long pavement line
    assert not _is_underline((100.0, 200.0, 100 + 20 * P, 200 + 2 * P), word)   # not level


def test_leader_to_a_word_note_is_not_template():
    import pymupdf as fitz

    class Img:                                              # page points = image pixels
        def to_view(self, x, y):
            return x, y

    def path(*pts):
        return {"items": [("l", fitz.Point(a), fitz.Point(b)) for a, b in zip(pts, pts[1:])]}

    # "EDGE OF STREAM BANK" at 10 px per ft; the leader rises from a catch point
    # and lands just short of the note
    note = TextSpan(330.0, 100.0, "EDGE", 7.0, 40.0, 7.0)
    boxes = [(note.x - _half_box(note)[0], note.y - _half_box(note)[1],
              note.x + _half_box(note)[0], note.y + _half_box(note)[1], True)]
    assert _is_landed_leader(path((200, 180), (290, 100), (306, 100)), Img(), 1.0, boxes, 10.0)
    # a template ending at a level stretch far from any note, or one that runs long, stays
    assert not _is_landed_leader(path((100, 180), (200, 100), (230, 100)), Img(), 1.0, boxes, 10.0)
    assert not _is_landed_leader(path((200, 180), (240, 100), (306, 100)), Img(), 1.0, boxes, 10.0)
    # a vertical label's box is tall and narrow, not as wide as its text is long
    assert _half_box(TextSpan(0, 0, "708.43", 7.0, 7.0, 40.0)) == (4.5, 21.0)


def test_template_carried_on_after_a_small_break():
    m = np.zeros((300, 1200), np.uint8)
    m[100, 100:600] = 1                                   # pavement + shoulder, 35 ft
    for i, x in enumerate(range(630, 760)):               # a slope starting 2.1 ft further on
        m[100 + i // 4, x] = 1
    m[40, 700:740] = 1                                     # a label underline, well above
    kept = template_strokes(m, int(2.0 * P), int(15 * P))
    assert kept[100:140, 630:760].any() and not kept[40].any()


def test_fuller_station_reading_wins_a_tie():
    # thin CAD strokes drop a digit: "102+50" read as "12+50"
    reads = [StationRead("102+09", 10209.0, 1.0, "ocr"),
             StationRead("12+50", 1250.0, 0.6, "ocr", candidates=("12+50", "102+50")),
             StationRead("103+00", 10300.0, 1.0, "ocr"),
             StationRead("103+50", 10350.0, 1.0, "ocr")]
    assert [r.label for r in repair(reads)] == ["102+09", "102+50", "103+00", "103+50"]


def test_title_border_one_square_below_is_not_a_grid_line(tmp_path):
    """A sheet border one grid square under the last section's axis must not be
    chained onto its grid (PLANS CALL 011: that section was lost)."""
    specs = [embankment("11+50", 651.3, 5.0), embankment("11+00", 651.7, 4.0)]
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [specs], border_below=True)
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    assert sorted(s.station_label for s in res.sections) == ["11+00", "11+50"]
