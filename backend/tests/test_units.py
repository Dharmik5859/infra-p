"""Unit tests for station repair, road grouping and the volume formula."""
import pytest

from gdot_earthwork.pages import parse_station
from gdot_earthwork.roads import StationEntry, group_into_roads
from gdot_earthwork.stations import StationRead, format_station, repair
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

