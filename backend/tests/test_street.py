"""Street names: read from the title block (the line under "CROSS SECTIONS"),
used as the road's label in the app and as streetName in the JSON."""
import pytest

from gdot_earthwork.plan_set import process_plan_set
from gdot_earthwork.roads import Road, StationEntry
from gdot_earthwork.street import _clean, name_roads, pretty, street_from_lines, street_from_name

from .synth import embankment, make_pdf


def _lines(*texts):
    return [(t, 0.0, float(i), 100.0) for i, t in enumerate(texts)]


@pytest.mark.parametrize("lines, want", [
    (("CROSS SECTIONS", "FRANKLIN GATEWAY OVER ROTTENWOOD CREEK"), "Franklin Gateway"),
    (("EARTHWORK CROSS SECTIONS", "CR 29/MARTINS MILL RD @ LITTLE RIVER"), "CR 29/Martins Mill Rd"),
    (("CROSS SECTIONS", "HORIZONTAL SCALE IN FEET", "SR 136", "BRIDGE REPLACEMENT"), "SR 136"),
    (("CROSS SECTIONS", "NEW HOPE RD AT WYLIE RD INTERSECTION", "NEW HOPE RD (WEST APPROACH)"),
     "New Hope Rd (West Approach)"),
    (("CROSS SECTIONS", "SR 332 & BOONE RD. IMPROVEMENTS", "DE2: SR 332"), "SR 332"),
    (("CROSS SECTIONS", "S.R. 5 CONNECTOR", "GEORGIA BYPASS"), "S.R. 5 Connector"),
    (("EARTHWORK CROSS SECTIONS", "Ase", "MOUNTAIN INDUSTRIAL BLVD", "2450 Commerce Avenue"), "Mountain Industrial Blvd"),
    (("CROSS SECTIONS", "RIVERSIDE ROAD CORRIDOR IMPROVEMENTS"), "Riverside Road"),
    (("CROSS SECTIONS", "SCALE IN FEET", "DRAWING No."), None),
])
def test_street_from_title_block(lines, want):
    assert street_from_lines(_lines(*lines)) == want


def test_cleaning_and_file_names():
    assert _clean("Avenue") is None and _clean("2450 Commerce Avenue") is None and _clean("MATCH EXISTING") is None
    assert _clean("—P— MOUNTAIN INDUSTRIAL BLVD") == "MOUNTAIN INDUSTRIAL BLVD" and _clean("I-75") == "I-75"
    assert pretty("SR 6 / US 278 / THORNTON ROAD") == "SR 6 / US 278 / Thornton Road"
    assert street_from_name("RIVER SIDE ROAD - EARTHWORK MAINLINE.pdf") == "River Side Road"
    assert street_from_name("SR 136 AT LOOKOUT CREEK- MAINLINE.pdf") == "SR 136"
    assert street_from_name("CALL 024 FULL PLAN.pdf") is None


def test_roads_named_by_their_sheets():
    class Sec:
        def __init__(self, street):
            self.street = street
    roads = [Road("Road 1", [StationEntry("1+00", 100, 1, Sec("SR 136")), StationEntry("1+50", 150, 1, Sec(None))]),
             Road("Road 2", [StationEntry("1+00", 100, 2, Sec("SR 136"))]),
             Road("Road 3", [StationEntry("5+00", 500, 3, Sec(None))])]
    roads[1].repeat_of = "Road 1"
    roads[1].flags = ["100% of these stations repeat Road 1 -- most likely the same alignment"]
    name_roads(roads)
    assert [r.label for r in roads] == ["SR 136", "SR 136 (2)", "Road 3"]
    assert roads[1].repeat_of == "SR 136" and "repeat SR 136 --" in roads[1].flags[0]
    name_roads(roads[2:], fallback="Lakeside Drive")
    assert roads[2].label == "Lakeside Drive"


@pytest.mark.parametrize("scanned", [False, True], ids=["vector", "scan"])
def test_street_read_from_the_sheet(tmp_path, scanned):
    pdf = tmp_path / "plans.pdf"
    make_pdf(str(pdf), [[embankment("11+50", 651.3, 5.0), embankment("11+00", 651.0, 4.0)]], scanned=scanned,
             title="CROSS SECTIONS\nCREEKVIEW WAY")
    res = process_plan_set(str(pdf), workers=1, overlays=False)
    assert {s.street for s in res.sections} == {"Creekview Way"}
    assert [r.label for r in res.roads] == ["Creekview Way"]
