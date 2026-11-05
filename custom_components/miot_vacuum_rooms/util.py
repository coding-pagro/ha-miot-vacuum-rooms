"""Reine Hilfsfunktionen ohne Home-Assistant-Abhängigkeit (leicht testbar)."""

from __future__ import annotations

import json
import re

_ENTITY_SUFFIX = re.compile(r"_(?P<kind>[ap])_(?P<siid>\d+)_(?P<num>\d+)$")


def parse_entity_suffix(entity_id: str) -> tuple[str, int, int] | None:
    """Zerlegt z. B. 'notify.x_start_clean_a_17_1' in ('a', 17, 1)."""
    match = _ENTITY_SUFFIX.search(entity_id)
    if not match:
        return None
    return match["kind"], int(match["siid"]), int(match["num"])


def build_start_message(clean_type: int, room_ids: list[int] | None = None) -> str:
    """Nachricht für start-clean: [clean-type, "clean-values"].

    Bestätigtes Beispiel (Raum 5): [3, "[5]"]
    """
    values = json.dumps(list(room_ids or []), separators=(",", ":"))
    return json.dumps([clean_type, values])


def build_value_message(value: int) -> str:
    """Nachricht für Einstellungen mit einem Zahlenwert, z. B. [2]."""
    return json.dumps([value])


def parse_clean_values(state: str | None) -> list[int] | None:
    """Liest den Sensor clean-values, z. B. '[12,6]' -> [12, 6].

    Gibt None zurück, wenn der Wert leer oder nicht auswertbar ist.
    Eine leere Liste '[]' (ganzes Stockwerk) wird als [] geliefert.
    """
    if state is None or state in ("", "unknown", "unavailable"):
        return None
    try:
        data = json.loads(state)
    except ValueError:
        return None
    if not isinstance(data, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in data
    ):
        return None
    return data


def parse_rooms_text(text: str) -> dict[str, int]:
    """Liest 'Name=ID' zeilenweise. Leere Zeilen und '#'-Kommentare entfallen.

    Wirft ValueError mit einer verständlichen Meldung bei Fehlern.
    """
    rooms: dict[str, int] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Zeile {number}: erwartet 'Name=ID'")
        name, _, value = line.rpartition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            raise ValueError(f"Zeile {number}: Name fehlt")
        if not value.isdigit():
            raise ValueError(f"Zeile {number}: ID muss eine ganze Zahl sein")
        if name in rooms:
            raise ValueError(f"Zeile {number}: Name '{name}' doppelt")
        rooms[name] = int(value)
    return rooms


def format_rooms_text(rooms: dict[str, int]) -> str:
    """Gegenstück zu parse_rooms_text für das Optionsformular."""
    return "\n".join(f"{name}={room_id}" for name, room_id in rooms.items())


def resolve_room_ids(rooms: dict[str, int], names: list[str]) -> list[int]:
    """Wandelt Raumnamen in IDs um, Reihenfolge der Eingabe bleibt erhalten.

    Wirft KeyError mit dem unbekannten Namen. Doppelte Namen werden entfernt.
    """
    ids: list[int] = []
    for name in names:
        if name not in rooms:
            raise KeyError(name)
        room_id = rooms[name]
        if room_id not in ids:
            ids.append(room_id)
    return ids
