"""Tests der eigenen Saugroboter-Entität."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN, VacuumEntityFeature
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.miot_vacuum_rooms.const import CONF_REQUIRE_DOCKED, DOMAIN

from .conftest import VACUUM, notify_id, sensor_id
from .test_integration import ROOMS, _setup

FEATURES = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.FAN_SPEED
    | VacuumEntityFeature.CLEAN_AREA
)


def _vacuum(hass: HomeAssistant, entry) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        VACUUM_DOMAIN, DOMAIN, f"{entry.entry_id}_vacuum"
    )
    assert entity_id
    return entity_id


def _messages(calls) -> list[tuple[str, str]]:
    return [(c.data["entity_id"], c.data["message"]) for c in calls]


def _source_calls(events) -> list[str]:
    """Dienste, die an den Xiaomi-Saugroboter (Quelle) gingen."""
    return [
        event.data["service"]
        for event in events
        if event.data["domain"] == VACUUM_DOMAIN
        and event.data["service_data"].get("entity_id") == VACUUM
    ]


async def _call(hass: HomeAssistant, service: str, entity_id: str, **data) -> None:
    await hass.services.async_call(
        VACUUM_DOMAIN, service, {"entity_id": entity_id, **data}, blocking=True
    )


def _set_registry_options(hass: HomeAssistant, entity_id: str, **options) -> None:
    er.async_get(hass).async_update_entity_options(entity_id, VACUUM_DOMAIN, options)


def _segments_issue(hass: HomeAssistant, entity_id: str):
    registry_id = er.async_get(hass).async_get(entity_id).id
    return ir.async_get(hass).async_get_issue(
        VACUUM_DOMAIN, f"segments_changed_{registry_id}"
    )


def _last_seen(rooms: dict[str, int]) -> list[dict]:
    return [{"id": str(i), "name": n, "group": None} for n, i in rooms.items()]


# --- Entität und Zustand -------------------------------------------------


async def test_entity_on_own_device(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    state = hass.states.get(entity_id)
    assert state.attributes["supported_features"] == FEATURES
    assert state.attributes["fan_speed_list"] == ["quiet", "standard", "strong", "max"]

    reg_entry = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(reg_entry.device_id)
    assert (DOMAIN, entry.entry_id) in device.identifiers
    # Hauptentität des Geräts: trägt den Gerätenamen
    assert state.name == "Robbi"


async def test_activity_follows_source(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    assert hass.states.get(entity_id).state == "docked"

    for value in ("cleaning", "paused", "returning", "idle", "error", "docked"):
        hass.states.async_set(VACUUM, value)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == value

    hass.states.async_set(VACUUM, "something_new")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"


@pytest.mark.parametrize("value", ["unavailable", "unknown"])
async def test_unavailable_with_source(
    hass: HomeAssistant, build_device, value: str
) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    hass.states.async_set(VACUUM, value)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"

    hass.states.async_set(VACUUM, "docked")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "docked"


# --- Start ----------------------------------------------------------------


async def test_start_cleans_all_rooms(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    events = async_capture_events(hass, EVENT_CALL_SERVICE)
    await _call(hass, "start", _vacuum(hass, entry))
    ids = ",".join(str(i) for i in ROOMS.values())
    assert _messages(calls) == [
        (notify_id("mode"), "[4]"),
        (notify_id("start"), f'[3, "[{ids}]"]'),
    ]
    assert _source_calls(events) == []


async def test_start_resumes_when_paused(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    hass.states.async_set(VACUUM, "paused")
    events = async_capture_events(hass, EVENT_CALL_SERVICE)
    await _call(hass, "start", _vacuum(hass, entry))
    assert _source_calls(events) == ["start"]
    assert calls == []


async def test_start_without_rooms(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device, rooms={})
    events = async_capture_events(hass, EVENT_CALL_SERVICE)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "start", _vacuum(hass, entry))
    assert err.value.translation_key == "no_rooms"
    assert calls == []
    assert _source_calls(events) == []


@pytest.mark.parametrize("value", ["idle", "cleaning", "returning"])
async def test_start_requires_dock(
    hass: HomeAssistant, build_device, value: str
) -> None:
    entry, calls = await _setup(hass, build_device)
    hass.states.async_set(VACUUM, value)
    events = async_capture_events(hass, EVENT_CALL_SERVICE)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "start", _vacuum(hass, entry))
    assert err.value.translation_key == "not_docked"
    assert calls == []
    assert _source_calls(events) == []


async def test_start_dock_check_can_be_disabled(
    hass: HomeAssistant, build_device
) -> None:
    entry, calls = await _setup(hass, build_device, **{CONF_REQUIRE_DOCKED: False})
    hass.states.async_set(VACUUM, "idle")
    hass.states.async_set(sensor_id("mode"), "Custom")
    await _call(hass, "start", _vacuum(hass, entry))
    assert [c.data["entity_id"] for c in calls] == [notify_id("start")]


# --- Durchreichen ---------------------------------------------------------


async def test_pause_stop_return_reach_source(
    hass: HomeAssistant, build_device
) -> None:
    entry, calls = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    hass.states.async_set(VACUUM, "cleaning")
    events = async_capture_events(hass, EVENT_CALL_SERVICE)
    for service in ("pause", "stop", "return_to_base"):
        await _call(hass, service, entity_id)
    assert _source_calls(events) == ["pause", "stop", "return_to_base"]
    assert calls == []


# --- Saugleistung ---------------------------------------------------------


async def test_fan_speed_follows_sensor(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    assert hass.states.get(entity_id).attributes["fan_speed"] == "quiet"

    hass.states.async_set(sensor_id("fan"), "Max")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["fan_speed"] == "max"

    hass.states.async_set(sensor_id("fan"), "unknown")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["fan_speed"] is None


async def test_set_fan_speed_sends_global_value(
    hass: HomeAssistant, build_device
) -> None:
    entry, calls = await _setup(hass, build_device)
    await _call(hass, "set_fan_speed", _vacuum(hass, entry), fan_speed="strong")
    assert _messages(calls) == [(notify_id("fan"), "[2]")]


async def test_set_fan_speed_unknown_value(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "set_fan_speed", _vacuum(hass, entry), fan_speed="turbo")
    assert calls == []


@pytest.mark.parametrize("value", ["cleaning", "paused"])
async def test_set_fan_speed_refused_during_customised_run(
    hass: HomeAssistant, build_device, value: str
) -> None:
    entry, calls = await _setup(hass, build_device)
    hass.states.async_set(VACUUM, value)
    hass.states.async_set(sensor_id("mode"), "Custom")
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "set_fan_speed", _vacuum(hass, entry), fan_speed="max")
    assert err.value.translation_key == "fan_speed_customised"
    assert calls == []


@pytest.mark.parametrize(
    ("vacuum_state", "mode"), [("cleaning", "OnlySweep"), ("docked", "Custom")]
)
async def test_set_fan_speed_allowed_otherwise(
    hass: HomeAssistant, build_device, vacuum_state: str, mode: str
) -> None:
    entry, calls = await _setup(hass, build_device)
    hass.states.async_set(VACUUM, vacuum_state)
    hass.states.async_set(sensor_id("mode"), mode)
    await _call(hass, "set_fan_speed", _vacuum(hass, entry), fan_speed="max")
    assert _messages(calls) == [(notify_id("fan"), "[3]")]


# --- Bereiche -------------------------------------------------------------


async def test_get_segments_returns_learned_rooms(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    entity = hass.data[VACUUM_DOMAIN].get_entity(_vacuum(hass, entry))
    segments = await entity.async_get_segments()
    assert [(s.id, s.name) for s in segments] == [
        (str(room_id), name) for name, room_id in ROOMS.items()
    ]


async def test_clean_area_keeps_order(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    areas = ar.async_get(hass)
    office = areas.async_create("Office").id
    kitchen = areas.async_create("Kitchen").id
    living = areas.async_create("Living room").id
    _set_registry_options(
        hass,
        entity_id,
        area_mapping={kitchen: ["4"], office: ["12"], living: ["3", "5"]},
        last_seen_segments=_last_seen(ROOMS),
    )
    await hass.async_block_till_done()

    await _call(hass, "clean_area", entity_id, cleaning_area_id=[office, living, kitchen])
    assert _messages(calls)[-1] == (notify_id("start"), '[3, "[12,3,5,4]"]')


async def test_clean_segments_unknown_id(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    entity = hass.data[VACUUM_DOMAIN].get_entity(_vacuum(hass, entry))
    with pytest.raises(ServiceValidationError) as err:
        await entity.async_clean_segments(["4", "99"])
    assert err.value.translation_key == "unknown_segment"
    assert calls == []


async def test_clean_area_requires_dock(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    _set_registry_options(hass, entity_id, area_mapping={kitchen: ["4"]})
    hass.states.async_set(VACUUM, "cleaning")
    with pytest.raises(ServiceValidationError):
        await _call(hass, "clean_area", entity_id, cleaning_area_id=[kitchen])
    assert calls == []


# --- Geänderte Segmente ---------------------------------------------------


async def _reload(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_no_issue_without_mapping(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    await _reload(hass, entry)
    assert _segments_issue(hass, _vacuum(hass, entry)) is None


async def test_no_issue_when_ids_equal(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    _set_registry_options(hass, entity_id, last_seen_segments=_last_seen(ROOMS))
    await _reload(hass, entry)
    assert _segments_issue(hass, entity_id) is None


async def test_no_issue_on_rename(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    renamed = {f"{name} (old)": room_id for name, room_id in ROOMS.items()}
    _set_registry_options(hass, entity_id, last_seen_segments=_last_seen(renamed))
    await _reload(hass, entry)
    assert _segments_issue(hass, entity_id) is None


async def test_issue_when_room_forgotten(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    _set_registry_options(hass, entity_id, last_seen_segments=_last_seen(ROOMS))
    await hass.async_block_till_done()
    assert _segments_issue(hass, entity_id) is None

    # Entfernen lädt den Eintrag neu, die Entität vergleicht beim Hinzufügen.
    await hass.services.async_call(
        DOMAIN, "forget_room", {"name": "Flur"}, blocking=True
    )
    await hass.async_block_till_done()
    assert _segments_issue(hass, entity_id) is not None


async def test_issue_when_ids_change_in_options(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    entity_id = _vacuum(hass, entry)
    _set_registry_options(hass, entity_id, last_seen_segments=_last_seen(ROOMS))
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"rooms": "Küche=4\nWohnzimmer=3\nFlur=5\nBüro=12\nBad=7", CONF_REQUIRE_DOCKED: True},
    )
    await hass.async_block_till_done()
    assert _segments_issue(hass, entity_id) is not None
