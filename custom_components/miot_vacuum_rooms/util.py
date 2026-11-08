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


def start_accepted(
    task: str | None,
    values: str | None,
    room_ids: list[int] | None,
    idle: tuple[str, ...],
) -> bool:
    """Prüft, ob der Roboter einen Start übernommen hat.

    Übernommen heißt: Auftragsstatus (p_17_9) ist bekannt und nicht Idle, und
    bei Raumreinigung enthält clean-values (p_17_34) genau die angeforderten
    IDs (Reihenfolge egal). room_ids=None steht für das ganze Stockwerk, dort
    zählt nur der Status.
    idle: Auftragsstatus ohne offenen Auftrag (const.TASK_IDLE).
    """
    if task is None or task in ("", "unknown", "unavailable") or task in idle:
        return False
    if room_ids is None:
        return True
    current = parse_clean_values(values)
    return current is not None and sorted(current) == sorted(room_ids)


_STATE_MAX_LENGTH = 255


def describe_current_rooms(
    state: str | None,
    rooms: dict[str, int],
    *,
    idle: str = "idle",
    whole_floor: str = "whole_floor",
) -> tuple[str | None, list[int], list[str]]:
    """Übersetzt clean-values (p_17_34) in (Zustand, Raum-IDs, Raumnamen).

    '' (zwischen den Läufen) -> idle, '[]' (ganzes Stockwerk) -> whole_floor,
    sonst die Raumnamen in der Reihenfolge des Rohwerts, mit ', ' verbunden.
    Nicht angelernte IDs erscheinen als 'ID n', doppelte IDs nur einmal.
    Haben mehrere Namen dieselbe ID, gilt der erste in der Raumtabelle.
    Nicht auswertbare Werte liefern (None, [], []).
    idle/whole_floor: Zustandswerte (const.CURRENT_ROOMS_*).
    """
    if state == "":
        return idle, [], []
    values = parse_clean_values(state)
    if values is None:
        return None, [], []
    if not values:
        return whole_floor, [], []
    names_by_id: dict[int, str] = {}
    for name, room_id in rooms.items():
        names_by_id.setdefault(room_id, name)
    room_ids = list(dict.fromkeys(values))
    names = [names_by_id.get(room_id, f"ID {room_id}") for room_id in room_ids]
    text = ", ".join(names)
    if len(text) > _STATE_MAX_LENGTH:
        text = text[: _STATE_MAX_LENGTH - 1] + "…"
    return text, room_ids, names
