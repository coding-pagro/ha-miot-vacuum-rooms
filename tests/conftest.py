"""Gemeinsame Fixtures: bildet das Gerät der Xiaomi-Home-Integration nach."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

PREFIX = "xtl_de_1234567890_xm2216"
VACUUM = f"vacuum.{PREFIX}"

NOTIFY = {
    "start": "start_clean_a_17_1",
    "fan": "set_fan_mode_a_17_26",
    "water": "set_water_mode_a_17_27",
    "count": "set_clean_count_a_17_28",
    "mode": "set_clean_mode_a_17_46",
    "route": "fine_drag_switch_a_17_50",
}
BUTTON = {
    "stop_clean": "stop_clean_a_17_3",
}
SENSOR = {
    "values": "clean_values_p_17_34",
    "task": "clean_type_status_p_17_9",
    "mode": "clean_mode_p_17_10",
    "fan": "fan_mode_p_17_13",
    "count": "clean_count_p_17_14",
    "route": "fine_drag_p_17_65",
    "error": "error_p_17_35",
    "station_error": "station_error_p_17_79",
    "water_tank": "clean_water_cistern_p_17_51",
}


def notify_id(key: str) -> str:
    return f"notify.{PREFIX}_{NOTIFY[key]}"


def sensor_id(key: str) -> str:
    return f"sensor.{PREFIX}_{SENSOR[key]}"


def button_id(key: str) -> str:
    return f"button.{PREFIX}_{BUTTON[key]}"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Lädt custom_components im Test."""
    yield


@pytest.fixture
def build_device(hass: HomeAssistant):
    """Legt Gerät und Entitäten wie in der Xiaomi-Home-Integration an."""

    def _build(skip: tuple[str, ...] = ()) -> str:
        host = MockConfigEntry(domain="xiaomi_home", title="Xiaomi Home")
        host.add_to_hass(hass)
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=host.entry_id, identifiers={("xiaomi_home", "xm2216")}
        )
        registry = er.async_get(hass)

        def add(domain: str, object_id: str) -> None:
            if any(part in object_id for part in skip):
                return
            registry.async_get_or_create(
                domain,
                "xiaomi_home",
                f"{domain}.{object_id}",
                suggested_object_id=object_id,
                config_entry=host,
                device_id=device.id,
            )

        registry.async_get_or_create(
            "vacuum",
            "xiaomi_home",
            "vacuum.main",
            suggested_object_id=PREFIX,
            config_entry=host,
            device_id=device.id,
        )
        for name in NOTIFY.values():
            add("notify", f"{PREFIX}_{name}")
        for name in SENSOR.values():
            add("sensor", f"{PREFIX}_{name}")
        for name in BUTTON.values():
            add("button", f"{PREFIX}_{name}")

        hass.states.async_set(VACUUM, "docked", {"friendly_name": "Robbi"})
        hass.states.async_set(sensor_id("mode"), "OnlySweep")
        hass.states.async_set(sensor_id("fan"), "Quiet")
        hass.states.async_set(sensor_id("count"), "Once")
        hass.states.async_set(sensor_id("route"), "Fine")
        hass.states.async_set(sensor_id("values"), "")
        hass.states.async_set(sensor_id("task"), "Idle")
        hass.states.async_set(sensor_id("error"), "0")
        hass.states.async_set(sensor_id("station_error"), "0")
        hass.states.async_set(sensor_id("water_tank"), "Normal")
        if not any(part in BUTTON["stop_clean"] for part in skip):
            # Tasten von Xiaomi Home haben bis zum ersten Drücken "unknown"
            hass.states.async_set(button_id("stop_clean"), "unknown")
        return VACUUM

    return _build
