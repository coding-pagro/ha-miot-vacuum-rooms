"""Tests für die reinen Hilfsfunktionen (ohne Home Assistant)."""

import importlib.util
import pathlib

import pytest

_PATH = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "miot_vacuum_rooms"
    / "util.py"
)
_spec = importlib.util.spec_from_file_location("miot_util", _PATH)
util = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(util)


def test_entity_suffix():
    assert util.parse_entity_suffix(
        "notify.xtl_de_1234567890_xm2216_start_clean_a_17_1"
    ) == ("a", 17, 1)
    assert util.parse_entity_suffix(
        "sensor.xtl_de_1234567890_xm2216_clean_values_p_17_34"
    ) == ("p", 17, 34)
    assert util.parse_entity_suffix("vacuum.xtl_de_1234567890_xm2216") is None
    # Ereignisse (e_) gehören nicht dazu
    assert util.parse_entity_suffix("event.x_map_data_report_e_17_1") is None


def test_start_message_matches_confirmed_commands():
    # Am Gerät bestätigt: Raum 5 = [3, "[5]"]
    assert util.build_start_message(3, [5]) == '[3, "[5]"]'
    # Mehrere Räume in der Reihenfolge der Eingabe
    assert util.build_start_message(3, [12, 6]) == '[3, "[12,6]"]'
    # Ganzes Stockwerk (abgeleitet, am Gerät nicht gesendet)
    assert util.build_start_message(1) == '[1, "[]"]'


def test_value_message():
    assert util.build_value_message(2) == "[2]"
    assert util.build_value_message(0) == "[0]"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("[5]", [5]),
        ("[12,6]", [12, 6]),
        ("[]", []),
        ("", None),
        ("unknown", None),
        ("unavailable", None),
        (None, None),
        ("abc", None),
        ('["a"]', None),
        ("[true]", None),
        ("5", None),
    ],
)
def test_parse_clean_values(state, expected):
    assert util.parse_clean_values(state) == expected


def test_rooms_text_roundtrip():
    text = "Küche=4\nWohnzimmer=3\n\n# Kommentar\nBad oben=6\n"
    rooms = util.parse_rooms_text(text)
    assert rooms == {"Küche": 4, "Wohnzimmer": 3, "Bad oben": 6}
    assert util.parse_rooms_text(util.format_rooms_text(rooms)) == rooms


@pytest.mark.parametrize(
    "text",
    ["Küche", "=4", "Küche=abc", "Küche=4\nKüche=5", "Küche=-1"],
)
def test_rooms_text_errors(text):
    with pytest.raises(ValueError):
        util.parse_rooms_text(text)


def test_resolve_room_ids():
    rooms = {"Küche": 4, "Wohnzimmer": 3, "Büro": 12}
    assert util.resolve_room_ids(rooms, ["Büro", "Küche"]) == [12, 4]
    # doppelte Namen werden entfernt
    assert util.resolve_room_ids(rooms, ["Küche", "Küche"]) == [4]
    with pytest.raises(KeyError):
        util.resolve_room_ids(rooms, ["Bad"])


@pytest.mark.parametrize(
    ("task", "values", "rooms", "expected"),
    [
        ("Area Clean", "[5]", [5], True),
        ("Area Clean", "[12,4]", [4, 12], True),
        ("Idle", "[5]", [5], False),
        ("None", "[5]", [5], False),
        (None, "[5]", [5], False),
        ("unknown", "[5]", [5], False),
        ("unavailable", "[5]", [5], False),
        ("Area Clean", "[4]", [5], False),
        ("Area Clean", "[5]", [5, 4], False),
        ("Area Clean", "[5,4]", [5], False),
        ("Area Clean", "", [5], False),
        ("Area Clean", None, [5], False),
        ("Full Clean", None, None, True),
        ("Full Clean", "[]", None, True),
        ("Idle", "[]", None, False),
    ],
)
def test_start_accepted(task, values, rooms, expected) -> None:
    assert util.start_accepted(task, values, rooms, ("Idle", "None")) is expected


_ROOMS = {"Küche": 12, "Bad": 6, "Flur": 3}


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("", ("idle", [], [])),
        ("[]", ("whole_floor", [], [])),
        ("[6]", ("Bad", [6], ["Bad"])),
        # Reihenfolge des Rohwerts, nicht der Raumtabelle
        ("[12,6]", ("Küche, Bad", [12, 6], ["Küche", "Bad"])),
        ("[6,12,3]", ("Bad, Küche, Flur", [6, 12, 3], ["Bad", "Küche", "Flur"])),
        # nicht angelernte ID
        ("[12,99]", ("Küche, ID 99", [12, 99], ["Küche", "ID 99"])),
        # doppelte IDs nur einmal, erste Position zählt
        ("[6,12,6]", ("Bad, Küche", [6, 12], ["Bad", "Küche"])),
        ("unknown", (None, [], [])),
        ("unavailable", (None, [], [])),
        (None, (None, [], [])),
        ("abc", (None, [], [])),
        ("[true]", (None, [], [])),
        ('["a"]', (None, [], [])),
        ("5", (None, [], [])),
    ],
)
def test_describe_current_rooms(state, expected) -> None:
    assert util.describe_current_rooms(state, _ROOMS) == expected


def test_describe_current_rooms_custom_state_values() -> None:
    assert util.describe_current_rooms("", {}, idle="i", whole_floor="w")[0] == "i"
    assert util.describe_current_rooms("[]", {}, idle="i", whole_floor="w")[0] == "w"


def test_describe_current_rooms_first_name_wins() -> None:
    # Im Textformat möglich: zwei Namen für dieselbe ID
    rooms = {"Küche": 4, "Bad": 4}
    assert util.describe_current_rooms("[4]", rooms) == ("Küche", [4], ["Küche"])


def test_describe_current_rooms_truncates_to_255() -> None:
    rooms = {f"Raum {i:02d} " + "x" * 20: i for i in range(20)}
    state, room_ids, names = util.describe_current_rooms(
        "[" + ",".join(str(i) for i in range(20)) + "]", rooms
    )
    assert len(state) == 255
    assert state.endswith("…")
    assert state[:-1] == ", ".join(names)[:254]
    # Attribute bleiben vollständig
    assert room_ids == list(range(20))
    assert len(names) == 20


def test_describe_current_rooms_exactly_255_not_truncated() -> None:
    name = "x" * 255
    state, _, _ = util.describe_current_rooms("[1]", {name: 1})
    assert state == name
