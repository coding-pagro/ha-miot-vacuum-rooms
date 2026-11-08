"""Diagnose-Datei mit geschwärzter Geräte-ID."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.miot_vacuum_rooms import diagnostics
from custom_components.miot_vacuum_rooms.const import (
    CONF_REQUIRE_DOCKED,
    CONF_ROOMS,
    CONF_SOURCES,
    DOMAIN,
)
from custom_components.miot_vacuum_rooms.discovery import discover_sources
from custom_components.miot_vacuum_rooms.source_health import ALL_ROLES

from .conftest import PREFIX, VACUUM, button_id, sensor_id

ROOMS = {"Küche": 4, "Flur": 5}
DEVICE_ID_DIGITS = "1234567890"  # Geräte-ID in PREFIX
IDENTIFIER = ("xiaomi_home", f"did-{DEVICE_ID_DIGITS}")


async def _setup(hass: HomeAssistant, build_device, *, before_setup=None):
    build_device()
    device_id = er.async_get(hass).async_get(VACUUM).device_id
    device = dr.async_get(hass).async_update_device(
        device_id,
        manufacturer="Xiaomi",
        model="xtl.vacuum.xm2216",
        sw_version="4.3.1",
        hw_version="1.0",
        new_identifiers={IDENTIFIER},
    )
    sources = discover_sources(hass, VACUUM)
    if before_setup is not None:
        before_setup()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robbi",
        unique_id=sources["vacuum"],
        data={CONF_SOURCES: sources},
        options={CONF_ROOMS: ROOMS, CONF_REQUIRE_DOCKED: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, sources, device


def _assert_no_secrets(result: dict, sources: dict[str, str], device) -> None:
    text = json.dumps(result)
    assert PREFIX not in text
    assert DEVICE_ID_DIGITS not in text
    assert device.id not in text
    for registry_id in sources.values():
        assert registry_id not in text
    assert IDENTIFIER[1] not in text


async def test_diagnostics(hass: HomeAssistant, build_device) -> None:
    entry, sources, device = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("task"), "Area Pause")

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"] == {
        "title": "Robbi",
        "version": entry.version,
        "options": {"rooms": ROOMS, "require_docked": False},
    }
    assert set(result["sources"]) == set(ALL_ROLES)
    assert result["sources"]["prop_values"] == {
        "entity_id": "sensor.xtl_de_**REDACTED**_xm2216_clean_values_p_17_34",
        "state": "",
        "disabled": False,
        "missing": False,
    }
    assert result["sources"]["vacuum"]["entity_id"] == "vacuum.xtl_de_**REDACTED**_xm2216"
    assert result["sources"]["vacuum"]["state"] == "docked"
    for info in result["sources"].values():
        assert "**REDACTED**" in info["entity_id"]
        assert not info["missing"]
        assert not info["disabled"]
    assert result["controller"] == {
        "use_app_room_settings": True,
        "job_pending": True,
        "job_paused": True,
        "problem": {"key": "none", "robot_error_code": 0, "station_error_code": 0},
    }
    assert result["device"] == {
        "manufacturer": "Xiaomi",
        "model": "xtl.vacuum.xm2216",
        "sw_version": "4.3.1",
        "hw_version": "1.0",
    }
    assert result["issues"] == {"missing_sources": False, "disabled_sources": False}
    _assert_no_secrets(result, sources, device)


async def test_diagnostics_missing_and_disabled(
    hass: HomeAssistant, build_device
) -> None:
    def before_setup() -> None:
        registry = er.async_get(hass)
        registry.async_remove(sensor_id("values"))
        hass.states.async_remove(sensor_id("values"))
        registry.async_update_entity(
            button_id("stop_clean"), disabled_by=er.RegistryEntryDisabler.USER
        )

    entry, sources, device = await _setup(
        hass, build_device, before_setup=before_setup
    )

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["sources"]["prop_values"] == {
        "entity_id": None,
        "state": None,
        "disabled": False,
        "missing": True,
    }
    stop = result["sources"]["act_stop_clean"]
    assert stop["disabled"] is True
    assert stop["missing"] is False
    assert stop["entity_id"] == "button.xtl_de_**REDACTED**_xm2216_stop_clean_a_17_3"
    assert result["issues"] == {"missing_sources": True, "disabled_sources": True}
    _assert_no_secrets(result, sources, device)


async def test_diagnostics_without_device(hass: HomeAssistant, build_device) -> None:
    """Keine Quelle existiert mehr: Gerät nicht bestimmbar."""

    def before_setup() -> None:
        registry = er.async_get(hass)
        for entity in er.async_entries_for_device(
            registry,
            registry.async_get(VACUUM).device_id,
            include_disabled_entities=True,
        ):
            registry.async_remove(entity.entity_id)
            hass.states.async_remove(entity.entity_id)

    entry, sources, device = await _setup(
        hass, build_device, before_setup=before_setup
    )

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["device"] is None
    assert all(info["missing"] for info in result["sources"].values())
    assert result["issues"]["missing_sources"] is True
    _assert_no_secrets(result, sources, device)
