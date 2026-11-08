"""Tests des Problemsensors und der Fehleranzeige der Saugroboter-Entität."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN, VacuumActivity
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.miot_vacuum_rooms.const import (
    CONF_ROOMS,
    CONF_SOURCES,
    DOMAIN,
)
from custom_components.miot_vacuum_rooms.discovery import discover_sources

from .conftest import VACUUM, sensor_id
from .test_integration import ROOMS, _setup


def _entity(hass: HomeAssistant, entry, domain: str, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{suffix}"
    )
    assert entity_id
    return entity_id


async def _states(hass: HomeAssistant, entry):
    await hass.async_block_till_done()
    sensor = hass.states.get(_entity(hass, entry, SENSOR_DOMAIN, "problem"))
    vacuum = hass.states.get(_entity(hass, entry, VACUUM_DOMAIN, "vacuum"))
    return sensor, vacuum


async def test_no_problem(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    sensor, vacuum = await _states(hass, entry)
    assert sensor.state == "none"
    assert sensor.attributes["robot_error_code"] == 0
    assert sensor.attributes["station_error_code"] == 0
    assert vacuum.state == VacuumActivity.DOCKED
    assert vacuum.attributes["problem"] is None


async def test_station_error_4502_and_back(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("task"), "Area Pause")
    hass.states.async_set(sensor_id("station_error"), "4502")
    sensor, vacuum = await _states(hass, entry)
    assert sensor.state == "station_4502"
    assert sensor.attributes["station_error_code"] == 4502
    assert vacuum.state == VacuumActivity.ERROR
    assert vacuum.attributes["problem"] == "station_4502"

    hass.states.async_set(sensor_id("station_error"), "0")
    sensor, vacuum = await _states(hass, entry)
    assert sensor.state == "none"
    assert vacuum.state == VacuumActivity.PAUSED
    assert vacuum.attributes["problem"] is None


@pytest.mark.parametrize(
    ("role", "expected"),
    [("error", "robot_unknown"), ("station_error", "station_unknown")],
)
async def test_unknown_code(
    hass: HomeAssistant, build_device, role: str, expected: str
) -> None:
    entry, _ = await _setup(hass, build_device)
    hass.states.async_set(sensor_id(role), "4003")
    sensor, vacuum = await _states(hass, entry)
    assert sensor.state == expected
    key = "robot_error_code" if role == "error" else "station_error_code"
    assert sensor.attributes[key] == 4003
    assert vacuum.state == VacuumActivity.ERROR
    assert vacuum.attributes["problem"] == expected


async def test_sources_unavailable(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("station_error"), "unavailable")
    sensor, vacuum = await _states(hass, entry)
    assert sensor.state == "unavailable"
    assert vacuum.state == VacuumActivity.DOCKED


async def test_existing_entry_gets_error_roles(
    hass: HomeAssistant, build_device
) -> None:
    """Einträge von vor den Fehler-Rollen bekommen sie beim Start ergänzt."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    new_roles = ("prop_error", "prop_station_error", "prop_water_tank")
    old = {r: i for r, i in sources.items() if r not in new_roles}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robbi",
        unique_id=sources["vacuum"],
        data={CONF_SOURCES: old},
        options={CONF_ROOMS: ROOMS},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.data[CONF_SOURCES] == sources
    assert entry.runtime_data.entity_id("prop_station_error") == sensor_id(
        "station_error"
    )
    hass.states.async_set(sensor_id("station_error"), "4502")
    sensor, _ = await _states(hass, entry)
    assert sensor.state == "station_4502"
