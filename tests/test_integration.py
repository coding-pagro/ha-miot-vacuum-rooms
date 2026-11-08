"""Tests gegen eine echte Home-Assistant-Testinstanz."""

from __future__ import annotations

import asyncio
import json

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.miot_vacuum_rooms.const import (
    CONF_REQUIRE_DOCKED,
    CONF_ROOMS,
    CONF_SOURCES,
    CONF_VACUUM,
    DOMAIN,
)
from custom_components.miot_vacuum_rooms.discovery import discover_sources

from .conftest import VACUUM, notify_id, sensor_id

ROOMS = {"Küche": 4, "Wohnzimmer": 3, "Flur": 5, "Büro": 12}


def robot_idle(hass: HomeAssistant) -> None:
    """Der Auftrag ist beendet (der Mock-Roboter setzt Status und Räume beim Start)."""
    hass.states.async_set(sensor_id("task"), "Idle")
    hass.states.async_set(sensor_id("values"), "")


async def _setup(
    hass: HomeAssistant,
    build_device,
    *,
    rooms=ROOMS,
    start_accepts=lambda attempt: True,
    **options,
):
    """Richtet die Integration ein und ersetzt notify.send_message durch einen Mock,
    der den Roboter nachahmt (Modus-Sensor folgt dem Befehl). Einen Start
    übernimmt der Roboter, wenn start_accepts(Nummer des Versuchs ab 1) wahr ist:
    Auftragsstatus und clean-values folgen dann dem Befehl."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robbi",
        unique_id=sources["vacuum"],
        data={CONF_SOURCES: sources},
        options={CONF_ROOMS: rooms, **options},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    calls: list[ServiceCall] = []
    mode_values = {"[0]": "BothWork", "[1]": "OnlySweep", "[4]": "Custom"}

    starts = 0

    async def _send_message(call: ServiceCall) -> None:
        nonlocal starts
        calls.append(call)
        if call.data["entity_id"] == notify_id("start"):
            starts += 1
            if start_accepts(starts):
                clean_type, values = json.loads(call.data["message"])
                hass.states.async_set(
                    sensor_id("task"), "Full Clean" if clean_type == 1 else "Area Clean"
                )
                hass.states.async_set(sensor_id("values"), values)
        if call.data["entity_id"] == notify_id("mode"):
            hass.states.async_set(
                sensor_id("mode"), mode_values[call.data["message"]]
            )

    hass.services.async_register("notify", "send_message", _send_message)
    return entry, calls


# --- Einrichtung ----------------------------------------------------------


async def test_config_flow_creates_entry(hass: HomeAssistant, build_device) -> None:
    build_device()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM: VACUUM}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Robbi"
    assert "act_start" in result["data"][CONF_SOURCES]
    assert "prop_values" in result["data"][CONF_SOURCES]


async def test_config_flow_reports_missing_entities(
    hass: HomeAssistant, build_device
) -> None:
    build_device(skip=("start_clean_a_17_1",))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM: VACUUM}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "missing_entities"}
    assert "a_17_1" in result["description_placeholders"]["missing"]


async def test_config_flow_rejects_duplicate(hass: HomeAssistant, build_device) -> None:
    await _setup(hass, build_device)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM: VACUUM}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["rooms", "learn"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rooms"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "rooms"

    bad = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ROOMS: "Küche", CONF_REQUIRE_DOCKED: True},
    )
    assert bad["errors"] == {CONF_ROOMS: "invalid_rooms"}

    done = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ROOMS: "Küche=4\nBad=7", CONF_REQUIRE_DOCKED: False},
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ROOMS] == {"Küche": 4, "Bad": 7}
    assert entry.options[CONF_REQUIRE_DOCKED] is False


async def _start_learning(hass: HomeAssistant, entry, name: str, timeout: int = 10):
    """Öffnet das Menü, wählt „Raum anlernen“ und sendet das Formular."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "learn"}
    )
    assert result["step_id"] == "learn"
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": name, "timeout": timeout}
    )


async def _finish_progress(hass: HomeAssistant, result):
    """Wartet, bis der Fortschrittsschritt abgeschlossen ist, und liefert den Folgeschritt."""
    for _ in range(100):
        if result["type"] is not FlowResultType.SHOW_PROGRESS:
            break
        await asyncio.sleep(0.02)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_configure(result["flow_id"])
    return result


async def test_options_learn_room_success(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    result = await _start_learning(hass, entry, " Gästezimmer ")
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "learning"

    # Der Wert vor dem Start zählt nicht, nur ein neuer Wechsel.
    hass.states.async_set(sensor_id("values"), "[11]")
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "learned"
    assert result["description_placeholders"] == {"room": "Gästezimmer", "id": "11"}

    done = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ROOMS]["Gästezimmer"] == 11
    assert er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_room_11"
    )


async def test_options_learn_room_replaces_name_of_known_id(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    result = await _start_learning(hass, entry, "Kochbereich")
    hass.states.async_set(sensor_id("values"), "[4]")
    result = await _finish_progress(hass, result)
    await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert "Küche" not in entry.options[CONF_ROOMS]
    assert entry.options[CONF_ROOMS]["Kochbereich"] == 4


async def test_options_learn_room_timeout_then_retry(
    hass: HomeAssistant, build_device, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, _ = await _setup(hass, build_device)
    before = dict(entry.options[CONF_ROOMS])

    # Erster Versuch: die Wartezeit läuft ab, ohne dass ein Raum gestartet wird.
    from custom_components.miot_vacuum_rooms import controller as controller_module

    real_wait = controller_module.async_wait_for_state
    calls = 0

    async def wait_once_without_change(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(0.05)
            return None
        return await real_wait(*args, **kwargs)

    monkeypatch.setattr(
        controller_module, "async_wait_for_state", wait_once_without_change
    )
    result = await _start_learning(hass, entry, "Gästezimmer", timeout=10)
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "learn_failed"
    assert result["errors"] == {"base": "learn_timeout"}
    assert result["description_placeholders"]["seconds"] == "10"
    assert entry.options[CONF_ROOMS] == before

    # Wiederholen: neues Formular, dann gilt wieder nur ein neuer Wechsel.
    again = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert again["step_id"] == "learn"
    again = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Gästezimmer", "timeout": 10}
    )
    assert again["type"] is FlowResultType.SHOW_PROGRESS
    hass.states.async_set(sensor_id("values"), "[11]")
    again = await _finish_progress(hass, again)
    assert again["step_id"] == "learned"


async def test_options_learn_room_rejects_multiple_rooms(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    before = dict(entry.options[CONF_ROOMS])
    result = await _start_learning(hass, entry, "X")
    hass.states.async_set(sensor_id("values"), "[12,6]")
    result = await _finish_progress(hass, result)
    assert result["step_id"] == "learn_failed"
    assert result["errors"] == {"base": "learn_not_single"}
    assert result["description_placeholders"]["ids"] == "[12,6]"
    assert entry.options[CONF_ROOMS] == before


async def test_options_learn_room_rejects_empty_name(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    before = dict(entry.options[CONF_ROOMS])
    result = await _start_learning(hass, entry, "   ")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "learn"
    assert result["errors"] == {"name": "empty_name"}
    assert entry.options[CONF_ROOMS] == before


# --- Räume reinigen -------------------------------------------------------


async def test_clean_rooms_sets_custom_mode_then_starts(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device)
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Büro", "Küche"]}, blocking=True
    )
    assert [(c.data["entity_id"], c.data["message"]) for c in calls] == [
        (notify_id("mode"), "[4]"),
        (notify_id("start"), '[3, "[12,4]"]'),
    ]


async def test_clean_rooms_skips_mode_if_already_custom(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert [(c.data["entity_id"], c.data["message"]) for c in calls] == [
        (notify_id("start"), '[3, "[5]"]'),
    ]


async def test_clean_rooms_requires_dock(hass: HomeAssistant, build_device) -> None:
    _, calls = await _setup(hass, build_device)
    hass.states.async_set(VACUUM, "idle")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "clean_rooms", {"rooms": ["Küche"]}, blocking=True
        )
    assert calls == []


async def test_clean_rooms_dock_check_can_be_disabled(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device, **{CONF_REQUIRE_DOCKED: False})
    hass.states.async_set(VACUUM, "idle")
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Küche"]}, blocking=True
    )
    assert len(calls) == 1


@pytest.mark.parametrize("task", ["Area Pause", "Area Clean", "Area Resume", "Full Pause"])
async def test_clean_rooms_refused_while_job_open(
    hass: HomeAssistant, build_device, task: str
) -> None:
    """Mitten im Auftrag meldet der Roboter beim Mopp-Waschen "docked"."""
    _, calls = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("task"), task)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "clean_rooms", {"rooms": ["Küche"]}, blocking=True
        )
    assert err.value.translation_key == "job_pending"
    assert calls == []


async def test_clean_rooms_job_check_off_with_dock_option(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device, **{CONF_REQUIRE_DOCKED: False})
    hass.states.async_set(sensor_id("task"), "Area Pause")
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Küche"]}, blocking=True
    )
    assert len(calls) == 1


@pytest.mark.parametrize("task", ["unavailable", "None"])
async def test_clean_rooms_without_job_status(
    hass: HomeAssistant, build_device, task: str
) -> None:
    """Kein Auftrag ("None") oder Status unbekannt: Verhalten wie vorher."""
    _, calls = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("task"), task)
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Küche"]}, blocking=True
    )
    assert len(calls) == 1


async def test_existing_entry_gets_new_source(hass: HomeAssistant, build_device) -> None:
    """Einträge von vor der Rolle prop_task bekommen sie beim Start ergänzt."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    old = {role: rid for role, rid in sources.items() if role != "prop_task"}
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
    assert entry.runtime_data.entity_id("prop_task") == sensor_id("task")


async def test_clean_rooms_unknown_room(hass: HomeAssistant, build_device) -> None:
    _, calls = await _setup(hass, build_device)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "clean_rooms", {"rooms": ["Bad"]}, blocking=True
        )
    assert calls == []


async def test_clean_rooms_unavailable_vacuum(
    hass: HomeAssistant, build_device
) -> None:
    _, calls = await _setup(hass, build_device)
    hass.states.async_set(VACUUM, "unavailable")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "clean_rooms", {"rooms": ["Küche"]}, blocking=True
        )
    assert calls == []


async def test_clean_floor(hass: HomeAssistant, build_device) -> None:
    _, calls = await _setup(hass, build_device)
    await hass.services.async_call(DOMAIN, "clean_floor", {}, blocking=True)
    assert [(c.data["entity_id"], c.data["message"]) for c in calls] == [
        (notify_id("start"), '[1, "[]"]'),
    ]


# --- Start-Verifikation -----------------------------------------------------


@pytest.fixture
def fast_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verkürzt das Warten auf die Übernahme auf wenige hundert Millisekunden."""
    monkeypatch.setattr(
        "custom_components.miot_vacuum_rooms.controller.START_CONFIRM_SECONDS", 0.2
    )


def _starts(calls) -> list[str]:
    return [c.data["message"] for c in calls if c.data["entity_id"] == notify_id("start")]


async def test_start_accepted_first_attempt(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(hass, build_device)
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert _starts(calls) == ['[3, "[5]"]']


async def test_start_accepted_second_attempt(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(hass, build_device, start_accepts=lambda n: n == 2)
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert _starts(calls) == ['[3, "[5]"]'] * 2


async def test_start_not_confirmed_after_three_attempts(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(hass, build_device, start_accepts=lambda n: False)
    hass.states.async_set(sensor_id("mode"), "Custom")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
        )
    assert err.value.translation_key == "start_not_confirmed"
    assert err.value.translation_placeholders == {"attempts": "3", "seconds": "0.2"}
    assert len(_starts(calls)) == 3


async def test_start_status_taken_but_rooms_differ_no_resend(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    """Status nicht mehr Idle, Räume stimmen nicht: nicht erneut senden."""

    def _wrong_rooms(attempt: int) -> bool:
        hass.states.async_set(sensor_id("task"), "Area Clean")
        hass.states.async_set(sensor_id("values"), "[4]")
        return False

    _, calls = await _setup(hass, build_device, start_accepts=_wrong_rooms)
    hass.states.async_set(sensor_id("mode"), "Custom")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert len(_starts(calls)) == 1


async def test_start_with_open_job_sends_once(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    """Ohne Docked-Prüfung und mit offenem Auftrag wird nicht verifiziert."""
    _, calls = await _setup(
        hass,
        build_device,
        start_accepts=lambda n: False,
        **{CONF_REQUIRE_DOCKED: False},
    )
    hass.states.async_set(sensor_id("mode"), "Custom")
    hass.states.async_set(sensor_id("task"), "Area Clean")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert len(_starts(calls)) == 1


async def test_start_without_sensor_sends_once(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(
        hass, build_device, start_accepts=lambda n: False
    )
    hass.states.async_set(sensor_id("mode"), "Custom")
    hass.states.async_set(sensor_id("values"), "unavailable")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert len(_starts(calls)) == 1


async def test_start_without_status_sensor_sends_once(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(hass, build_device, start_accepts=lambda n: False)
    hass.states.async_set(sensor_id("mode"), "Custom")
    hass.states.async_set(sensor_id("task"), "unavailable")
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {"rooms": ["Flur"]}, blocking=True
    )
    assert len(_starts(calls)) == 1


async def test_clean_floor_retries_on_status_only(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(hass, build_device, start_accepts=lambda n: n == 2)
    await hass.services.async_call(DOMAIN, "clean_floor", {}, blocking=True)
    assert _starts(calls) == ['[1, "[]"]'] * 2


async def test_clean_floor_not_confirmed(
    hass: HomeAssistant, build_device, fast_confirm
) -> None:
    _, calls = await _setup(hass, build_device, start_accepts=lambda n: False)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "clean_floor", {}, blocking=True)
    assert len(_starts(calls)) == 3


# --- Anlernen -------------------------------------------------------------


async def test_learn_room_stores_id_and_creates_button(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "learn_room",
            {"name": "Gästezimmer", "timeout": 10},
            blocking=True,
            return_response=True,
        )
    )
    await asyncio.sleep(0.05)
    # Der Wert vor dem Aufruf zählt nicht, nur ein neuer Wechsel.
    hass.states.async_set(sensor_id("values"), "[11]")
    result = await asyncio.wait_for(task, 5)
    await hass.async_block_till_done()

    assert result == {"room": "Gästezimmer", "id": 11}
    assert entry.options[CONF_ROOMS]["Gästezimmer"] == 11
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_room_11")


async def test_learn_room_renames_existing_id(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "learn_room",
            {"name": "Kochbereich", "timeout": 10},
            blocking=True,
            return_response=True,
        )
    )
    await asyncio.sleep(0.05)
    hass.states.async_set(sensor_id("values"), "[4]")
    await asyncio.wait_for(task, 5)
    assert "Küche" not in entry.options[CONF_ROOMS]
    assert entry.options[CONF_ROOMS]["Kochbereich"] == 4


async def test_learn_room_rejects_multiple_rooms(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN, "learn_room", {"name": "X", "timeout": 10}, blocking=True
        )
    )
    await asyncio.sleep(0.05)
    hass.states.async_set(sensor_id("values"), "[12,6]")
    with pytest.raises(ServiceValidationError):
        await asyncio.wait_for(task, 5)
    assert "X" not in entry.options[CONF_ROOMS]


async def test_forget_room(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    await hass.services.async_call(
        DOMAIN, "forget_room", {"name": "Küche"}, blocking=True
    )
    await hass.async_block_till_done()
    assert "Küche" not in entry.options[CONF_ROOMS]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "forget_room", {"name": "Küche"}, blocking=True
        )


# --- Entitäten ------------------------------------------------------------


def _select(hass: HomeAssistant, entry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id, key
    return entity_id


async def test_selects_follow_sensors(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    assert hass.states.get(_select(hass, entry, "mode")).state == "sweep"
    assert hass.states.get(_select(hass, entry, "fan")).state == "quiet"
    assert hass.states.get(_select(hass, entry, "count")).state == "once"
    assert hass.states.get(_select(hass, entry, "route")).state == "deep"

    hass.states.async_set(sensor_id("mode"), "SweepFirst")
    hass.states.async_set(sensor_id("route"), "Daily")
    hass.states.async_set(sensor_id("fan"), "Auto")
    await hass.async_block_till_done()
    assert hass.states.get(_select(hass, entry, "mode")).state == "sweep_then_mop"
    assert hass.states.get(_select(hass, entry, "route")).state == "daily"
    assert hass.states.get(_select(hass, entry, "fan")).state == "standard"


async def test_select_sends_command(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": _select(hass, entry, "fan"), "option": "strong"},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": _select(hass, entry, "route"), "option": "fast"},
        blocking=True,
    )
    assert [(c.data["entity_id"], c.data["message"]) for c in calls] == [
        (notify_id("fan"), "[2]"),
        (notify_id("route"), "[0]"),
    ]


async def test_water_select_is_optimistic(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    entity_id = _select(hass, entry, "water")
    assert hass.states.get(entity_id).state in ("unknown", "unavailable")
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "high"},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "high"
    assert [(c.data["entity_id"], c.data["message"]) for c in calls] == [
        (notify_id("water"), "[2]"),
    ]


async def test_button_press_starts_room(hass: HomeAssistant, build_device) -> None:
    entry, calls = await _setup(hass, build_device)
    entity_id = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_room_5"
    )
    assert entity_id
    assert hass.states.get(entity_id) is not None
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    assert calls[-1].data["message"] == '[3, "[5]"]'


async def test_unload(hass: HomeAssistant, build_device) -> None:
    entry, _ = await _setup(hass, build_device)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED


# --- Anlernen im Dialog: weitere Pfade --------------------------------------


async def test_options_learn_room_aborts_when_entry_not_loaded(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    assert await hass.config_entries.async_unload(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "learn"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_loaded"


async def test_options_learn_room_close_dialog_cancels_wait(
    hass: HomeAssistant, build_device
) -> None:
    entry, _ = await _setup(hass, build_device)
    before = dict(entry.options[CONF_ROOMS])
    result = await _start_learning(hass, entry, "Gästezimmer")
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    hass.config_entries.options.async_abort(result["flow_id"])
    await hass.async_block_till_done()
    hass.states.async_set(sensor_id("values"), "[11]")
    await hass.async_block_till_done()
    assert entry.options[CONF_ROOMS] == before


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (HomeAssistantError("kaputt"), "kaputt"),
        (RuntimeError("unerwartet"), "unerwartet"),
        (asyncio.CancelledError(), "cancelled"),
    ],
)
async def test_options_learn_room_other_errors_show_failed_step(
    hass: HomeAssistant, build_device, monkeypatch: pytest.MonkeyPatch, error, expected
) -> None:
    from custom_components.miot_vacuum_rooms.controller import VacuumController

    entry, _ = await _setup(hass, build_device)

    async def fail(self, name, timeout):
        await asyncio.sleep(0.05)
        raise error

    monkeypatch.setattr(VacuumController, "async_learn_room", fail)
    result = await _start_learning(hass, entry, "X")
    result = await _finish_progress(hass, result)
    assert result["step_id"] == "learn_failed"
    assert result["errors"] == {"base": "learn_failed"}
    assert result["description_placeholders"]["error"] == expected
