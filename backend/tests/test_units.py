"""Unit tests for station repair, road grouping, the volume formula and
tracing helpers."""
import cv2
import numpy as np
import pytest

from gdot_earthwork.pages import parse_station
from gdot_earthwork.roads import StationEntry, group_into_roads
from gdot_earthwork.stations import StationRead, format_station, repair
from gdot_earthwork.tracing import drop_layer_lines
from gdot_earthwork.volume import average_end_area_volume


def read(label, conf=1.0, cands=()):
    return StationRead(label, parse_station(label) if label else None, conf,
                       "ocr" if label else None, candidates=cands)


def labels(reads):
    return [(r.label, r.source) for r in reads]


def test_parse_and_format_station():
    assert parse_station("12+50") == 1250
    assert parse_station("97+50.00") == 9750
    assert parse_station("1+2") is None
    assert format_station(1250) == "12+50"
    assert format_station(9750, 2) == "97+50.00"


def test_repair_picks_the_ocr_reading_that_fits():
    seq = [read("90+00.00"), read("904+50.00", 0.6, ("90+50.00", "904+50.00")),
           read("91+00.00"), read("914+50.00", 0.6, ("91+50.00", "914+50.00")), read("92+00.00")]
    assert labels(repair(seq)) == [("90+00.00", "ocr"), ("90+50.00", "ocr"), ("91+00.00", "ocr"),
                                   ("91+50.00", "ocr"), ("92+00.00", "ocr")]


def test_repair_infers_dropped_digit_and_missing_label():
    seq = [read(None, 0), read("12+00"), read("12+50"), read("13+00"), read("3+50"), read("14+00"), read("14+50")]
    out = labels(repair(seq))
    assert out[0] == ("11+50", "inferred")
    assert out[4] == ("13+50", "inferred")
    assert out[1:4] == [("12+00", "ocr"), ("12+50", "ocr"), ("13+00", "ocr")]


def test_repair_keeps_inserted_stations_and_road_changes():
    seq = [read("26+00"), read("26+40", 0.6), read("26+50"), read("27+00"), read("1+00"), read("1+50"), read("2+00")]
    assert [r.label for r in repair(seq)] == ["26+00", "26+40", "26+50", "27+00", "1+00", "1+50", "2+00"]


def entries(*stations):
    return [StationEntry(format_station(s), s, i) for i, s in enumerate(stations)]


def test_roads_split_on_station_restart_and_flag_repeats():
    roads = group_into_roads(entries(1000, 1050, 1100, 1150, 1000, 1050, 1100, 200, 250))
    assert [len(r.entries) for r in roads] == [4, 3, 2]
    assert roads[1].repeat_of == roads[0].label
    assert roads[2].repeat_of is None


def test_roads_flag_missing_section_gap():
    roads = group_into_roads(entries(1000, 1050, 1100, 1250, 1300))
    assert len(roads) == 1
    assert any("gap" in f for f in roads[0].flags)


def test_average_end_area_volume():
    S = lambda st, f, c: type("S", (), dict(station_label=format_station(st), station_ft=st, fill_ft2=f, cut_ft2=c))()
    v = average_end_area_volume([S(1000, 100, 0), S(1050, 200, 27)])
    assert v.segments[0].fill_cy == pytest.approx((100 + 200) / 2 * 50 / 27, abs=0.01)
    assert v.segments[0].cut_cy == pytest.approx(27 / 2 * 50 / 27, abs=0.01)
    assert v.total_net_cy == pytest.approx(v.total_fill_cy - v.total_cut_cy)


def test_repair_overrules_confident_ocr_when_neighbours_agree():
    seq = [read("96+00.00"), read("964+50.00", 1.0, ("964+50.00",)), read("97+00.00"), read("97+50.00")]
    assert [r.label for r in repair(seq)] == ["96+00.00", "96+50.00", "97+00.00", "97+50.00"]


def test_repair_never_touches_text_labels_or_new_roads():
    t = StationRead("5+00", 500.0, 1.0, "text")
    seq = [read("49+00"), read("49+54"), read("60+00"), read("60+50"), read("61+00"), t, read("5+50")]
    assert [r.label for r in repair(seq)] == ["49+00", "49+54", "60+00", "60+50", "61+00", "5+00", "5+50"]



def _dashes(m, x0, x1, y0, y1):
    """Dashed line from (x0, y0) to (x1, y1): 12 px on, 8 px off."""
    for x in range(x0, x1, 20):
        xe = min(x + 12, x1)
        ya = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        yb = y0 + (y1 - y0) * (xe - x0) / (x1 - x0)
        cv2.line(m, (x, int(round(ya))), (xe, int(round(yb))), 1, 2)


def test_layer_line_under_template_is_not_ground():
    template = np.zeros((300, 600), np.uint8)
    cv2.line(template, (100, 100), (500, 140), 1, 2)           # 10 % cross slope
    dash = np.zeros_like(template)
    _dashes(dash, 0, 140, 100, 104)                             # ground, running onto the old road
    _dashes(dash, 150, 450, 123, 153)                           # pavement bottom: parallel, 18 px down
    _dashes(dash, 120, 480, 160, 200)                           # real ground: diverges from the grade
    kept = drop_layer_lines(dash, template)
    assert kept[:, :100].any()                                  # the ground itself stays
    assert not kept[115:135, 200:210].any()                     # the parallel layer line is gone
    assert kept[160:180, 200:210].any()                         # diverging ground under fill stays


def test_ground_parallel_to_a_thin_raise_is_kept():
    template = np.zeros((300, 600), np.uint8)
    cv2.line(template, (100, 100), (500, 140), 1, 2)
    dash = np.zeros_like(template)
    _dashes(dash, 0, 600, 108, 148)                             # one continuous ground line, 8 px down
    assert drop_layer_lines(dash, template).sum() == dash.sum()


def test_repair_drops_digit_ocr_inserted_before_plus():
    reads = [read("300+00"), read("300+50"), read("301+00"), read("3014+50"), read("3024+00"),
             read("3024+50"), read("303+00"), read("303+50")]
    assert [r.label for r in repair(reads)] == [
        "300+00", "300+50", "301+00", "301+50", "302+00", "302+50", "303+00", "303+50"]


def test_repair_fixes_a_run_of_dropped_leading_digits():
    # OCR loses the "7" on a whole sheet series; the run is self-consistent
    # but breaks the road's sequence at both ends
    seq = ["68+00", "68+50", "69+00", "69+50", "0+00", "0+50", "11+00", "11+50", "12+00",
           "12+50", "13+00", "13+50", "74+00", "74+50"]
    # as on the real sheets, some renderings did read the 7
    alt = {"0+50": ("70+50",), "11+00": ("71+00",), "12+00": ("72+00",), "13+00": ("73+00",)}
    out = repair([read(x, cands=(x, *alt.get(x, ()))) for x in seq])
    assert [r.label for r in out] == [f"{68 + i // 2}+{'50' if i % 2 else '00'}" for i in range(len(seq))]
    assert all(r.source in ("inferred", "ocr") for r in out[4:12])
    assert out[4].source == "inferred"                          # a correction nobody read is flagged


def test_repair_keeps_the_history_through_unreadable_labels():
    # Perry Creek page 8: a badly misread label followed by three unreadable
    # ones; the next real reading shows they were 56+00 .. 57+50
    seq = ["54+50", "55+00", "55+50", "764+00", None, None, None, "58+00", "58+50"]
    out = repair([read(x) for x in seq])
    assert [r.label for r in out] == ["54+50", "55+00", "55+50", "56+00", "56+50", "57+00", "57+50",
                                      "58+00", "58+50"]
    assert all(r.source == "inferred" for r in out[3:7])
