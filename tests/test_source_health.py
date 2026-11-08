"""Selbstheilung der Quellen und Reparaturmeldungen."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.miot_vacuum_rooms import source_health
from custom_components.miot_vacuum_rooms.const import (
    CONF_DEVICE_ID,
    CONF_ROOMS,
    CONF_SOURCES,
    DOMAIN,
)
from custom_components.miot_vacuum_rooms.discovery import (
    NoDeviceError,
    discover_sources,
    find_sources,
    role_label,
)

from .conftest import VACUUM, button_id, notify_id, sensor_id

ROOMS = {"Küche": 4}


def _issue(hass: HomeAssistant, key: str, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{entry.entry_id}")


def _remove(hass: HomeAssistant, entity_id: str) -> er.RegistryEntry:
    """Entfernt eine Entität samt Zustand (wie Xiaomi Home beim Entfernen)."""
    registry = er.async_get(hass)
    old = registry.async_get(entity_id)
    assert old is not None
    registry.async_remove(entity_id)
    hass.states.async_remove(entity_id)
    return old


def _create(
    hass: HomeAssistant, old: er.RegistryEntry, tag: str = "new", state: str = "0"
) -> str:
    """Legt eine entfernte Entität mit neuer Registry-ID und gleicher Entitäts-ID an."""
    new = er.async_get(hass).async_get_or_create(
        old.domain,
        old.platform,
        f"{old.unique_id}-{tag}",
        suggested_object_id=old.entity_id.split(".", 1)[1],
        config_entry=hass.config_entries.async_get_entry(old.config_entry_id),
        device_id=old.device_id,
    )
    assert new.entity_id == old.entity_id
    assert new.id != old.id
    hass.states.async_set(new.entity_id, state)
    return new.id


def _recreate(hass: HomeAssistant, entity_id: str, tag: str = "new") -> str:
    """Entfernt eine Entität und legt sie mit neuer Registry-ID wieder an.

    So verhält sich Xiaomi Home, wenn es eine Entität neu erzeugt.
    Liefert die neue Registry-ID.
    """
    state = hass.states.get(entity_id)
    return _create(hass, _remove(hass, entity_id), tag, state.state if state else "0")


def _add_vacuum(hass: HomeAssistant, unique_id: str, *, platform: str = "xiaomi_home") -> str:
    """Hängt eine weitere Vacuum-Entität an das Xiaomi-Gerät."""
    registry = er.async_get(hass)
    device_id = registry.async_get(notify_id("start")).device_id
    return registry.async_get_or_create(
        "vacuum", platform, unique_id, device_id=device_id
    ).id


def _device_id(hass: HomeAssistant) -> str:
    """device_id des Xiaomi-Geräts (über die Vacuum-Entität)."""
    return er.async_get(hass).async_get(VACUUM).device_id


async def _setup_entry(
    hass: HomeAssistant,
    sources: dict[str, str],
    *,
    unique_id: str | None = None,
    device_id: str | None = None,
) -> MockConfigEntry:
    data = {CONF_SOURCES: sources}
    if device_id is not None:
        data[CONF_DEVICE_ID] = device_id
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robbi",
        unique_id=unique_id or sources.get("vacuum", "robbi"),
        data=data,
        options={CONF_ROOMS: ROOMS},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_dead_source_is_healed(hass: HomeAssistant, build_device) -> None:
    """Xiaomi Home hat eine Quelle neu angelegt: die neue Registry-ID wird übernommen."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    new_id = _recreate(hass, sensor_id("values"))

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["prop_values"] == new_id
    assert entry.runtime_data.entity_id("prop_values") == sensor_id("values")
    assert _issue(hass, "missing_sources", entry) is None


async def test_dead_source_healed_on_reload(hass: HomeAssistant, build_device) -> None:
    build_device()
    sources = discover_sources(hass, VACUUM)
    entry = await _setup_entry(hass, sources)

    new_id = _recreate(hass, notify_id("start"))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_SOURCES]["act_start"] == new_id
    assert entry.runtime_data.entity_id("act_start") == notify_id("start")
    assert _issue(hass, "missing_sources", entry) is None


async def test_missing_required_source_creates_issue(
    hass: HomeAssistant, build_device
) -> None:
    """Eine Pflichtquelle fehlt ganz: Meldung mit Liste, das Setup klappt trotzdem."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    _remove(hass, sensor_id("values"))

    entry = await _setup_entry(hass, sources)

    issue = _issue(hass, "missing_sources", entry)
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.ERROR
    assert not issue.is_fixable
    assert issue.translation_key == "missing_sources"
    assert issue.translation_placeholders == {
        "title": "Robbi",
        "entities": "sensor p_17_34",
    }
    assert entry.runtime_data.entity_id("prop_values") is None


async def test_issue_disappears_when_source_returns(
    hass: HomeAssistant, build_device
) -> None:
    build_device()
    sources = discover_sources(hass, VACUUM)
    old = _remove(hass, sensor_id("values"))
    entry = await _setup_entry(hass, sources)
    assert _issue(hass, "missing_sources", entry) is not None

    new_id = _create(hass, old, state="")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_SOURCES]["prop_values"] == new_id
    assert _issue(hass, "missing_sources", entry) is None


async def test_dead_vacuum_found_via_other_source(
    hass: HomeAssistant, build_device
) -> None:
    """Die Vacuum-Quelle ist tot, das Gerät wird über eine andere Quelle gefunden."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    new_id = _recreate(hass, VACUUM)

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["vacuum"] == new_id
    assert entry.unique_id == new_id
    assert entry.runtime_data.entity_id("vacuum") == VACUUM
    assert _issue(hass, "missing_sources", entry) is None


async def test_no_source_left(hass: HomeAssistant, build_device) -> None:
    """Keine Quelle existiert mehr: nichts zu heilen, die Meldung nennt alle."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    registry = er.async_get(hass)
    for registry_id in sources.values():
        _remove(hass, registry.async_get(registry_id).entity_id)

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES] == sources
    issue = _issue(hass, "missing_sources", entry)
    assert issue is not None
    entities = issue.translation_placeholders["entities"].split(", ")
    assert entities[0] == "vacuum"
    assert "notify a_17_1" in entities
    assert "sensor p_17_34" in entities
    assert len(entities) == 16  # vacuum + 15 Pflichtrollen
    assert "button a_17_3" not in entities
    assert _issue(hass, "disabled_sources", entry) is None


async def test_missing_optional_source_no_issue(
    hass: HomeAssistant, build_device
) -> None:
    build_device(skip=("stop_clean",))
    sources = discover_sources(hass, VACUUM)
    assert "act_stop_clean" not in sources

    entry = await _setup_entry(hass, sources)

    assert "act_stop_clean" not in entry.data[CONF_SOURCES]
    assert _issue(hass, "missing_sources", entry) is None
    assert _issue(hass, "disabled_sources", entry) is None


async def test_disabled_source_creates_warning(
    hass: HomeAssistant, build_device
) -> None:
    build_device()
    sources = discover_sources(hass, VACUUM)
    registry = er.async_get(hass)
    registry.async_update_entity(
        button_id("stop_clean"), disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await _setup_entry(hass, sources)

    issue = _issue(hass, "disabled_sources", entry)
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert not issue.is_fixable
    assert issue.translation_key == "disabled_sources"
    assert issue.translation_placeholders == {
        "title": "Robbi",
        "entities": button_id("stop_clean"),
    }
    assert _issue(hass, "missing_sources", entry) is None

    registry.async_update_entity(button_id("stop_clean"), disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, "disabled_sources", entry) is None


async def test_valid_source_not_replaced(hass: HomeAssistant, build_device) -> None:
    """Eine zweite Entität mit gleicher Endung ändert eine gültige Zuordnung nicht."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    registry = er.async_get(hass)
    old = registry.async_get(sensor_id("values"))
    host = hass.config_entries.async_get_entry(old.config_entry_id)
    registry.async_get_or_create(
        "sensor",
        "xiaomi_home",
        "values-second",
        suggested_object_id="aaa_other_clean_values_p_17_34",
        config_entry=host,
        device_id=old.device_id,
    )
    _remove(hass, notify_id("start"))  # erzwingt eine Heilung

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["prop_values"] == sources["prop_values"]


async def test_partial_heal(hass: HomeAssistant, build_device) -> None:
    """Eine tote ID wird ersetzt, eine andere Pflichtrolle fehlt weiter."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    new_id = _recreate(hass, sensor_id("task"))
    _remove(hass, notify_id("route"))

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["prop_task"] == new_id
    assert entry.data[CONF_SOURCES]["act_route"] == sources["act_route"]
    issue = _issue(hass, "missing_sources", entry)
    assert issue is not None
    assert issue.translation_placeholders["entities"] == "notify a_17_50"


async def test_nothing_to_heal_no_update(hass: HomeAssistant, build_device) -> None:
    build_device()
    sources = discover_sources(hass, VACUUM)
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        entry = await _setup_entry(hass, sources, device_id=_device_id(hass))
    assert update.call_count == 0
    assert entry.data[CONF_SOURCES] == sources


async def test_dead_vacuum_two_candidates_not_healed(
    hass: HomeAssistant, build_device
) -> None:
    build_device()
    sources = discover_sources(hass, VACUUM)
    _remove(hass, VACUUM)
    _add_vacuum(hass, "first")
    _add_vacuum(hass, "second")

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["vacuum"] == sources["vacuum"]
    assert entry.unique_id == sources["vacuum"]
    issue = _issue(hass, "missing_sources", entry)
    assert issue is not None
    assert issue.translation_placeholders["entities"] == "vacuum"


async def test_dead_vacuum_one_candidate_healed(
    hass: HomeAssistant, build_device
) -> None:
    """Eigene Vacuum-Entitäten (Plattform miot_vacuum_rooms) zählen nicht mit."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    _remove(hass, VACUUM)
    new_id = _add_vacuum(hass, "replacement")
    _add_vacuum(hass, "own", platform=DOMAIN)

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["vacuum"] == new_id
    assert entry.unique_id == new_id
    assert _issue(hass, "missing_sources", entry) is None


async def test_dead_vacuum_owned_by_other_entry_not_healed(
    hass: HomeAssistant, build_device
) -> None:
    """Der Ersatz gehört schon einem neu eingerichteten Eintrag: keine Übernahme."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    _remove(hass, VACUUM)
    new_id = _add_vacuum(hass, "replacement")
    other = MockConfigEntry(
        domain=DOMAIN,
        title="Robbi neu",
        unique_id=new_id,
        data={CONF_SOURCES: {**sources, "vacuum": new_id}},
        options={CONF_ROOMS: ROOMS},
    )
    other.add_to_hass(hass)  # nicht geladen, belegt aber die unique_id

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES]["vacuum"] == sources["vacuum"]
    assert entry.unique_id == sources["vacuum"]
    issue = _issue(hass, "missing_sources", entry)
    assert issue is not None
    assert issue.translation_placeholders["entities"] == "vacuum"


async def test_renamed_source_needs_no_heal(hass: HomeAssistant, build_device) -> None:
    """Neue Entitäts-ID, gleiche Registry-ID: keine Heilung, keine Meldung."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    device_id = _device_id(hass)
    er.async_get(hass).async_update_entity(
        sensor_id("task"), new_entity_id="sensor.renamed_task"
    )
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        entry = await _setup_entry(hass, sources, device_id=device_id)
    assert update.call_count == 0
    assert entry.runtime_data.entity_id("prop_task") == "sensor.renamed_task"
    assert _issue(hass, "missing_sources", entry) is None


async def test_remove_entry_deletes_issues(hass: HomeAssistant, build_device) -> None:
    build_device()
    sources = discover_sources(hass, VACUUM)
    registry = er.async_get(hass)
    _remove(hass, sensor_id("values"))
    registry.async_update_entity(
        button_id("stop_clean"), disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await _setup_entry(hass, sources)
    assert _issue(hass, "missing_sources", entry) is not None
    assert _issue(hass, "disabled_sources", entry) is not None

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, "missing_sources", entry) is None
    assert _issue(hass, "disabled_sources", entry) is None


# --- Erneute Prüfung bei Registry-Änderungen ----------------------------


async def _after_cooldown(hass: HomeAssistant) -> None:
    """Spult über den Cooldown der Prüfung hinaus."""
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=source_health.CHECK_COOLDOWN + 1)
    )
    await hass.async_block_till_done()


def _count_checks():
    """Zählt Aufrufe der Heilung (die Prüfung ruft sie immer auf)."""
    return patch.object(
        source_health,
        "async_heal_sources",
        wraps=source_health.async_heal_sources,
    )


def _count_updates(hass: HomeAssistant):
    return patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    )


def _own_vacuum(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        VACUUM_DOMAIN, DOMAIN, f"{entry.entry_id}_vacuum"
    )
    assert entity_id
    return entity_id


async def test_runtime_removal_creates_issue(hass: HomeAssistant, build_device) -> None:
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))

    _remove(hass, sensor_id("values"))
    await hass.async_block_till_done()
    assert _issue(hass, "missing_sources", entry) is None  # noch im Cooldown

    await _after_cooldown(hass)
    issue = _issue(hass, "missing_sources", entry)
    assert issue is not None
    assert issue.translation_placeholders["entities"] == "sensor p_17_34"


async def test_runtime_recreate_heals_and_reloads(
    hass: HomeAssistant, build_device
) -> None:
    """Neu angelegt: geheilt, neu geladen, Meldung weg, die Entitäten folgen."""
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))
    old = _remove(hass, sensor_id("error"))
    await _after_cooldown(hass)
    assert _issue(hass, "missing_sources", entry) is not None
    controller = entry.runtime_data

    new_id = _create(hass, old, state="7")
    await _after_cooldown(hass)

    assert entry.data[CONF_SOURCES]["prop_error"] == new_id
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not controller  # neu geladen
    assert _issue(hass, "missing_sources", entry) is None
    # Die Saugroboter-Entität liest den Fehlercode der neuen Quelle
    assert hass.states.get(_own_vacuum(hass, entry)).state == "error"


async def test_runtime_disable_and_enable(hass: HomeAssistant, build_device) -> None:
    """Deaktivieren/Aktivieren: Meldung kommt und geht, ohne Neuladen."""
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))
    controller = entry.runtime_data
    registry = er.async_get(hass)

    with _count_updates(hass) as update:
        registry.async_update_entity(
            sensor_id("task"), disabled_by=er.RegistryEntryDisabler.USER
        )
        await _after_cooldown(hass)
        issue = _issue(hass, "disabled_sources", entry)
        assert issue is not None
        assert issue.translation_placeholders["entities"] == sensor_id("task")

        registry.async_update_entity(sensor_id("task"), disabled_by=None)
        await _after_cooldown(hass)
        assert _issue(hass, "disabled_sources", entry) is None

    assert update.call_count == 0
    assert entry.runtime_data is controller


async def test_many_events_one_check(hass: HomeAssistant, build_device) -> None:
    """Ein Update von Xiaomi Home mit vielen Neuanlagen: eine Prüfung, ein Neuladen."""
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))
    keys = ("start", "fan", "water", "count", "mode", "route")

    with _count_checks() as checks, _count_updates(hass) as update:
        for key in keys:
            _recreate(hass, notify_id(key))
        await hass.async_block_till_done()
        await _after_cooldown(hass)

    # Nur die entprellte Prüfung (das Setup ruft die Heilung über __init__ auf)
    assert checks.call_count == 1
    assert update.call_count == 1
    assert entry.state is ConfigEntryState.LOADED
    for key in keys:
        assert entry.runtime_data.entity_id(f"act_{key}") == notify_id(key)
    assert _issue(hass, "missing_sources", entry) is None


async def test_irrelevant_event_no_check(hass: HomeAssistant, build_device) -> None:
    build_device()
    await _setup_entry(hass, discover_sources(hass, VACUUM))
    registry = er.async_get(hass)

    with _count_checks() as checks:
        other = registry.async_get_or_create("sensor", "other", "other-1")
        registry.async_update_entity(other.entity_id, new_entity_id="sensor.renamed")
        registry.async_remove("sensor.renamed")
        # Quelle, aber eine Änderung ohne Belang
        registry.async_update_entity(sensor_id("task"), name="Task")
        await _after_cooldown(hass)

    assert checks.call_count == 0


async def test_no_check_after_unload(hass: HomeAssistant, build_device) -> None:
    """Nach dem Entladen bleibt eine schon geplante Prüfung aus."""
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))

    with _count_checks() as checks:
        _remove(hass, sensor_id("values"))
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        await _after_cooldown(hass)
        _remove(hass, sensor_id("task"))
        await _after_cooldown(hass)

    assert checks.call_count == 0
    assert _issue(hass, "missing_sources", entry) is None


async def test_runtime_xiaomi_vacuum_recreated(
    hass: HomeAssistant, build_device
) -> None:
    """Xiaomi Home legt die Vacuum-Entität (ohne Endung) neu an: geheilt."""
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))

    old = _remove(hass, VACUUM)
    new_id = _create(hass, old, state="docked")
    await _after_cooldown(hass)

    assert entry.data[CONF_SOURCES]["vacuum"] == new_id
    assert entry.unique_id == new_id
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.entity_id("vacuum") == VACUUM
    assert _issue(hass, "missing_sources", entry) is None


async def test_runtime_new_entity_on_device_triggers_check(
    hass: HomeAssistant, build_device
) -> None:
    """Eine neue Entität ohne Endung am Xiaomi-Gerät löst eine Prüfung aus."""
    build_device()
    await _setup_entry(hass, discover_sources(hass, VACUUM))

    with _count_checks() as checks:
        _add_vacuum(hass, "another")
        await _after_cooldown(hass)

    assert checks.call_count == 1


async def test_runtime_rename_source(hass: HomeAssistant, build_device) -> None:
    """Umbenennung einer Quelle: Prüfung läuft, nichts zu heilen, keine Meldung."""
    build_device()
    entry = await _setup_entry(hass, discover_sources(hass, VACUUM))

    with _count_checks() as checks, _count_updates(hass) as update:
        er.async_get(hass).async_update_entity(
            sensor_id("task"), new_entity_id="sensor.renamed_task"
        )
        await _after_cooldown(hass)

    assert checks.call_count == 1
    assert update.call_count == 0
    assert entry.runtime_data.entity_id("prop_task") == "sensor.renamed_task"
    assert _issue(hass, "missing_sources", entry) is None
    assert _issue(hass, "disabled_sources", entry) is None


# --- Gespeichertes Gerät und Entladen ------------------------------------


def _recreate_all(hass: HomeAssistant, sources: dict[str, str]) -> None:
    """Xiaomi Home legt alle Quellen neu an (neue Registry-IDs, gleiches Gerät)."""
    registry = er.async_get(hass)
    for registry_id in sources.values():
        _recreate(hass, registry.async_get(registry_id).entity_id)


async def test_device_id_stored_once(hass: HomeAssistant, build_device) -> None:
    """Einträge ohne gespeichertes Gerät bekommen es beim ersten Laden, danach nie wieder."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    entry = await _setup_entry(hass, sources)
    assert entry.data[CONF_DEVICE_ID] == _device_id(hass)
    assert entry.data[CONF_SOURCES] == sources

    with _count_updates(hass) as update:
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert update.call_count == 0


async def test_all_sources_recreated_healed_via_stored_device(
    hass: HomeAssistant, build_device
) -> None:
    """Keine gespeicherte ID gilt mehr: das gespeicherte Gerät hilft beim Laden."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    device_id = _device_id(hass)
    _recreate_all(hass, sources)

    entry = await _setup_entry(hass, sources, device_id=device_id)

    healed = entry.data[CONF_SOURCES]
    assert set(healed) == set(sources)
    assert not set(healed.values()) & set(sources.values())
    assert entry.unique_id == healed["vacuum"]
    assert entry.runtime_data.entity_id("vacuum") == VACUUM
    assert entry.runtime_data.entity_id("prop_values") == sensor_id("values")
    assert _issue(hass, "missing_sources", entry) is None


async def test_all_sources_recreated_without_stored_device(
    hass: HomeAssistant, build_device
) -> None:
    """Ohne gespeichertes Gerät (alter Eintrag) lässt sich nichts heilen."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    _recreate_all(hass, sources)

    entry = await _setup_entry(hass, sources)

    assert entry.data[CONF_SOURCES] == sources
    assert CONF_DEVICE_ID not in entry.data
    assert _issue(hass, "missing_sources", entry) is not None


async def test_runtime_all_sources_recreated(hass: HomeAssistant, build_device) -> None:
    """Xiaomi Home legt zur Laufzeit alle Quellen neu an: geheilt nach dem Cooldown."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    entry = await _setup_entry(hass, sources)

    _recreate_all(hass, sources)
    await _after_cooldown(hass)

    healed = entry.data[CONF_SOURCES]
    assert not set(healed.values()) & set(sources.values())
    assert entry.unique_id == healed["vacuum"]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.entity_id("act_start") == notify_id("start")
    assert _issue(hass, "missing_sources", entry) is None


async def test_disabled_entry_has_no_issues(hass: HomeAssistant, build_device) -> None:
    """Deaktivieren entlädt den Eintrag und entfernt die Meldungen; Aktivieren bringt sie zurück."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    registry = er.async_get(hass)
    _remove(hass, sensor_id("values"))
    registry.async_update_entity(
        button_id("stop_clean"), disabled_by=er.RegistryEntryDisabler.USER
    )
    entry = await _setup_entry(hass, sources)
    assert _issue(hass, "missing_sources", entry) is not None
    assert _issue(hass, "disabled_sources", entry) is not None

    assert await hass.config_entries.async_set_disabled_by(
        entry.entry_id, ConfigEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert _issue(hass, "missing_sources", entry) is None
    assert _issue(hass, "disabled_sources", entry) is None

    assert await hass.config_entries.async_set_disabled_by(entry.entry_id, None)
    await hass.async_block_till_done()
    assert _issue(hass, "missing_sources", entry) is not None
    assert _issue(hass, "disabled_sources", entry) is not None


# --- Weitere Randfälle -----------------------------------------------------


def test_role_label() -> None:
    assert role_label("vacuum") == "vacuum"
    assert role_label("act_start") == "notify a_17_1"
    assert role_label("prop_values") == "sensor p_17_34"
    assert role_label("act_stop_clean") == "button a_17_3"


async def test_find_sources_ignores_other_services(
    hass: HomeAssistant, build_device
) -> None:
    """Endungen anderer Dienste (siid != 17) zählen nicht, auch bei gleicher Nummer."""
    build_device(skip=("clean_values_p_17_34",))
    registry = er.async_get(hass)
    device_id = _device_id(hass)
    registry.async_get_or_create(
        "sensor", "xiaomi_home", "other-service", suggested_object_id="x_p_2_34",
        device_id=device_id,
    )

    found, missing = find_sources(hass, device_id)

    assert "prop_values" not in found
    assert missing == ["sensor p_17_34"]


async def test_discover_sources_without_device(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    entity = registry.async_get_or_create("vacuum", "xiaomi_home", "no-device")
    with pytest.raises(NoDeviceError):
        discover_sources(hass, entity.entity_id)


async def test_sources_without_vacuum_role(hass: HomeAssistant, build_device) -> None:
    """Fehlt die Rolle vacuum ganz, wird das Gerät über eine andere Quelle gefunden."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    without_vacuum = {role: rid for role, rid in sources.items() if role != "vacuum"}

    entry = await _setup_entry(hass, without_vacuum, unique_id=sources["vacuum"])

    assert entry.data[CONF_SOURCES]["vacuum"] == sources["vacuum"]
    assert _issue(hass, "missing_sources", entry) is None


async def test_runtime_source_restored_with_same_id(
    hass: HomeAssistant, build_device
) -> None:
    """Xiaomi Home legt eine entfernte Entität mit gleicher unique_id wieder an.

    Home Assistant vergibt dann die alte Registry-ID: nichts zu heilen, die
    Meldung verschwindet trotzdem.
    """
    build_device()
    sources = discover_sources(hass, VACUUM)
    entry = await _setup_entry(hass, sources)
    old = _remove(hass, VACUUM)
    await _after_cooldown(hass)
    assert _issue(hass, "missing_sources", entry) is not None

    with _count_updates(hass) as update:
        restored = er.async_get(hass).async_get_or_create(
            old.domain,
            old.platform,
            old.unique_id,
            suggested_object_id=old.entity_id.split(".", 1)[1],
            config_entry=hass.config_entries.async_get_entry(old.config_entry_id),
            device_id=old.device_id,
        )
        hass.states.async_set(restored.entity_id, "docked")
        await _after_cooldown(hass)

    assert restored.id == sources["vacuum"]
    assert update.call_count == 0
    assert _issue(hass, "missing_sources", entry) is None
