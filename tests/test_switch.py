"""Tests des Schalters „Raumeinstellungen der App verwenden“."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import mock_restore_cache

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.miot_vacuum_rooms.const import DOMAIN

from .conftest import VACUUM, notify_id, sensor_id
from .test_integration import _setup, robot_idle

SWITCH = "switch.robbi_use_room_settings_from_the_app"


def _messages(calls) -> list[tuple[str, str]]:
    return [(c.data["entity_id"], c.data["message"]) for c in calls]


async def _turn(hass: HomeAssistant, on: bool) -> None:
    await hass.services.async_call(
        "switch", "turn_on" if on else "turn_off", {"entity_id": SWITCH}, blocking=True
    )


async def _clean(hass: HomeAssistant, *rooms: str) -> None:
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": list(rooms)}, blocking=True
    )


async def test_switch_default_on(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    assert (
        er.async_get(hass).async_get_entity_id(
            "switch", DOMAIN, f"{entry.entry_id}_use_app_room_settings"
        )
        == SWITCH
    )
    assert hass.states.get(SWITCH).state == "on"
    assert entry.runtime_data.use_app_room_settings is True

    await _clean(hass, "Flur")
    assert _messages(calls) == [
        (notify_id("mode"), "[4]"),
        (notify_id("start"), '[3, "[5]"]'),
    ]


async def test_switch_off_keeps_global_mode(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    await _turn(hass, False)
    assert hass.states.get(SWITCH).state == "off"
    assert entry.runtime_data.use_app_room_settings is False

    await _clean(hass, "Büro", "Küche")
    assert _messages(calls) == [(notify_id("start"), '[3, "[12,4]"]')]

    await _turn(hass, True)
    robot_idle(hass)
    calls.clear()
    await _clean(hass, "Flur")
    assert [m for _, m in _messages(calls)] == ["[4]", '[3, "[5]"]']


async def test_switch_off_refuses_custom_mode(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device)
    await _turn(hass, False)
    hass.states.async_set(sensor_id("mode"), "Custom")
    with pytest.raises(ServiceValidationError) as err:
        await _clean(hass, "Flur")
    assert err.value.translation_key == "custom_mode_with_global_settings"
    assert calls == []


async def test_switch_off_still_requires_dock(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device)
    await _turn(hass, False)
    hass.states.async_set(VACUUM, "cleaning")
    with pytest.raises(ServiceValidationError) as err:
        await _clean(hass, "Flur")
    assert err.value.translation_key == "not_docked"
    assert calls == []


async def test_switch_off_applies_to_vacuum_and_buttons(
    hass: HomeAssistant, build_device
) -> None:
    entry, calls = await _setup(hass, build_device)
    await _turn(hass, False)
    registry = er.async_get(hass)

    vacuum = registry.async_get_entity_id("vacuum", DOMAIN, f"{entry.entry_id}_vacuum")
    await hass.services.async_call(
        "vacuum", "start", {"entity_id": vacuum}, blocking=True
    )
    robot_idle(hass)
    button = registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_room_5")
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    assert [entity for entity, _ in _messages(calls)] == [
        notify_id("start"),
        notify_id("start"),
    ]


async def test_switch_state_restored(hass: HomeAssistant, build_device) -> None:
    mock_restore_cache(hass, [State(SWITCH, "off")])
    entry, calls = await _setup(hass, build_device)
    assert hass.states.get(SWITCH).state == "off"
    assert entry.runtime_data.use_app_room_settings is False

    await _clean(hass, "Flur")
    assert _messages(calls) == [(notify_id("start"), '[3, "[5]"]')]


async def test_switch_state_survives_reload(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    await _turn(hass, False)
    # Raum entfernen lädt den Eintrag neu, der Controller wird neu erzeugt.
    await hass.services.async_call(
        DOMAIN, "forget_room", {"name": "Küche"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == "off"
    assert entry.runtime_data.use_app_room_settings is False
