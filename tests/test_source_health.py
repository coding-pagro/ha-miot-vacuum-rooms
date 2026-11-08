"""Selbstheilung der Quellen und Reparaturmeldungen."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.miot_vacuum_rooms.const import CONF_ROOMS, CONF_SOURCES, DOMAIN
from custom_components.miot_vacuum_rooms.discovery import discover_sources

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


async def _setup_entry(
    hass: HomeAssistant, sources: dict[str, str], *, unique_id: str | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robbi",
        unique_id=unique_id or sources.get("vacuum", "robbi"),
        data={CONF_SOURCES: sources},
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
        entry = await _setup_entry(hass, sources)
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


async def test_renamed_source_needs_no_heal(hass: HomeAssistant, build_device) -> None:
    """Neue Entitäts-ID, gleiche Registry-ID: keine Heilung, keine Meldung."""
    build_device()
    sources = discover_sources(hass, VACUUM)
    er.async_get(hass).async_update_entity(
        sensor_id("task"), new_entity_id="sensor.renamed_task"
    )
    with patch.object(
        hass.config_entries,
        "async_update_entry",
        wraps=hass.config_entries.async_update_entry,
    ) as update:
        entry = await _setup_entry(hass, sources)
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
