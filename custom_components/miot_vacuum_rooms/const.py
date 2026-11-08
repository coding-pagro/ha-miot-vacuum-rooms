"""Konstanten für MIoT Saugroboter Räume.

Alle Nummern stammen aus der MIoT-Spezifikation des Jonr P20 Pro
(xtl.vacuum.xm2216), Dienst 17 "robotic-vacuum". Die Zuordnung der
Sensorwerte und Befehle wurde am echten Gerät bestätigt (siehe README).
"""

from __future__ import annotations

DOMAIN = "miot_vacuum_rooms"

CONF_VACUUM = "vacuum_entity_id"
CONF_SOURCES = "sources"  # Rolle -> Registry-ID der Quell-Entität
CONF_ROOMS = "rooms"  # Name -> Raum-ID (Optionen)
CONF_REQUIRE_DOCKED = "require_docked"

DEFAULT_REQUIRE_DOCKED = True

# Dienst-Nummern (siid), gilt für die gesamte Spezifikation
SIID = 17

# Rolle -> (Art, Nummer). "a" = Aktion (notify-Entität), "p" = Eigenschaft (Sensor)
# Der Suffix steht am Ende der Entitäts-ID der Xiaomi-Home-Integration,
# z. B. notify.<gerät>_start_clean_a_17_1 oder sensor.<gerät>_fan_mode_p_17_13.
ROLES: dict[str, tuple[str, int]] = {
    "act_start": ("a", 1),
    "act_fan": ("a", 26),
    "act_water": ("a", 27),
    "act_count": ("a", 28),
    "act_mode": ("a", 46),
    "act_route": ("a", 50),
    "prop_values": ("p", 34),
    "prop_task": ("p", 9),
    "prop_mode": ("p", 10),
    "prop_fan": ("p", 13),
    "prop_count": ("p", 14),
    "prop_route": ("p", 65),
}

# clean-type für start-clean
CLEAN_TYPE_FULL = 1  # nur abgeleitet, am Gerät NICHT gesendet
CLEAN_TYPE_AREA = 3  # bestätigt

# Auswahlfelder: Schlüssel -> (Aktionsrolle, Sensorrolle oder None, Werte)
# Werte: Optionsschlüssel -> (Befehlswert, Sensorzustand oder None)
SELECTS: dict[str, dict] = {
    "mode": {
        "action": "act_mode",
        "sensor": "prop_mode",
        "options": {
            "both": (0, "BothWork"),  # App: "Saugen&Wischen"
            "sweep": (1, "OnlySweep"),  # App: "Saugen"
            "mop": (2, "OnlyMop"),  # App: "Wischen"
            "sweep_then_mop": (3, "SweepFirst"),  # App: "Saugen und wischen"
            "custom": (4, "Custom"),  # App: "Personalisieren"
        },
    },
    "fan": {
        "action": "act_fan",
        "sensor": "prop_fan",
        "options": {
            "quiet": (0, "Quiet"),
            "standard": (1, "Auto"),
            "strong": (2, "Strong"),
            "max": (3, "Max"),
        },
    },
    "water": {
        "action": "act_water",
        "sensor": None,  # kein Sensor vorhanden, Wert wird nur gemerkt
        "options": {
            "low": (0, None),
            "medium": (1, None),
            "high": (2, None),
        },
    },
    "count": {
        "action": "act_count",
        "sensor": "prop_count",
        "options": {
            "once": (1, "Once"),
            "twice": (2, "Twice"),
        },
    },
    "route": {
        "action": "act_route",
        "sensor": "prop_route",
        "options": {
            "fast": (0, "Fast"),  # App: "Schnell"
            "daily": (1, "Daily"),  # App: "Täglich"
            "deep": (2, "Fine"),  # App: "Tief"
        },
    },
}

MODE_CUSTOM = "custom"

# Auftragsstatus (clean-type-status, p_17_9), am Gerät beobachtet:
# Idle, Area Clean/Pause/Resume, Full Clean/Pause. Während eines Auftrags
# meldet der Xiaomi-Saugroboter beim Mopp-Waschen "docked", der Auftrag
# steht dann auf "... Pause". Nur "Idle" (oder "None") heißt: kein Auftrag offen.
TASK_IDLE = ("Idle", "None")
TASK_PAUSE_SUFFIX = " Pause"

# Start-Verifikation: Die Cloud bestätigt Befehle, die der Roboter nicht
# ausführt (z. B. bei Stationswäsche oder Akku-Zyklus). Nach dem Senden wird
# bis zu START_CONFIRM_SECONDS auf die Übernahme gewartet, dann erneut gesendet.
# Werte sind am Gerät noch nicht gemessen.
START_CONFIRM_SECONDS = 25
START_ATTEMPTS = 3

SERVICE_CLEAN_ROOMS = "clean_rooms"
SERVICE_CLEAN_FLOOR = "clean_floor"
SERVICE_LEARN_ROOM = "learn_room"
SERVICE_FORGET_ROOM = "forget_room"

ATTR_ENTRY_ID = "entry_id"
ATTR_ROOMS = "rooms"
ATTR_NAME = "name"
ATTR_TIMEOUT = "timeout"

WAIT_MODE_SECONDS = 10
LEARN_TIMEOUT_DEFAULT = 90
