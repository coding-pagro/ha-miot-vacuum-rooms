"""Tests des Sensors "Räume im aktuellen Lauf" (clean-values p_17_34)."""

from __future__ import annotations

import pytest

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.miot_vacuum_rooms.const import CONF_ROOMS, DOMAIN

from .conftest import sensor_id
from .test_integration import ROOMS, _setup

VALUES = sensor_id("values")


def _sensor_id(hass: HomeAssistant, entry) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        SENSOR_DOMAIN, DOMAIN, f"{entry.entry_id}_current_rooms"
    )
    assert entity_id
    return entity_id


async def _state(hass: HomeAssistant, entry):
    await hass.async_block_till_done()
    return hass.states.get(_sensor_id(hass, entry))


async def _set(hass: HomeAssistant, entry, value: str):
    hass.states.async_set(VALUES, value)
    return await _state(hass, entry)


async def test_idle(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _state(hass, entry)
    assert sensor.state == "idle"
    assert sensor.attributes["room_ids"] == []
    assert sensor.attributes["rooms"] == []


async def test_run_with_learned_rooms(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _set(hass, entry, "[12,4]")
    # Reihenfolge aus p_17_34, nicht aus der Raumtabelle
    assert sensor.state == "Büro, Küche"
    assert sensor.attributes["room_ids"] == [12, 4]
    assert sensor.attributes["rooms"] == ["Büro", "Küche"]


async def test_unknown_id(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _set(hass, entry, "[4,99,4]")
    assert sensor.state == "Küche, ID 99"
    assert sensor.attributes["room_ids"] == [4, 99]
    assert sensor.attributes["rooms"] == ["Küche", "ID 99"]


async def test_whole_floor(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _set(hass, entry, "[]")
    assert sensor.state == "whole_floor"
    assert sensor.attributes["room_ids"] == []
    assert sensor.attributes["rooms"] == []


async def test_run_back_to_idle_clears_attributes(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _set(hass, entry, "[5]")
    assert sensor.state == "Flur"
    assert sensor.attributes["room_ids"] == [5]
    sensor = await _set(hass, entry, "")
    assert sensor.state == "idle"
    assert sensor.attributes["room_ids"] == []
    assert sensor.attributes["rooms"] == []


@pytest.mark.parametrize("value", ["unknown", "abc", "[true]"])
async def test_unreadable_value(hass: HomeAssistant, build_device, value) -> None:
    entry, _ = await _setup(hass, build_device)
    await _set(hass, entry, "[5]")
    sensor = await _set(hass, entry, value)
    assert sensor.state == STATE_UNKNOWN
    assert sensor.attributes["room_ids"] == []
    assert sensor.attributes["rooms"] == []


async def test_source_unavailable_and_back(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _set(hass, entry, STATE_UNAVAILABLE)
    assert sensor.state == STATE_UNAVAILABLE
    sensor = await _set(hass, entry, "[3]")
    assert sensor.state == "Wohnzimmer"
    assert sensor.attributes["room_ids"] == [3]


async def test_source_missing(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    assert entry.runtime_data.entity_id("prop_values") == VALUES
    er.async_get(hass).async_remove(VALUES)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.entity_id("prop_values") is None
    sensor = await _state(hass, entry)
    assert sensor.state == STATE_UNAVAILABLE


async def test_registry(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    registry_entry = er.async_get(hass).async_get(_sensor_id(hass, entry))
    assert registry_entry.unique_id == f"{entry.entry_id}_current_rooms"
    assert registry_entry.entity_category is None
    assert registry_entry.translation_key == "current_rooms"
    device = dr.async_get(hass).async_get(registry_entry.device_id)
    assert device.identifiers == entry.runtime_data.device_info["identifiers"]


async def test_new_room_after_reload(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor = await _set(hass, entry, "[11]")
    assert sensor.state == "ID 11"
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ROOMS: {**ROOMS, "Gästezimmer": 11}}
    )
    sensor = await _state(hass, entry)
    assert sensor.state == "Gästezimmer"
    assert sensor.attributes["rooms"] == ["Gästezimmer"]
