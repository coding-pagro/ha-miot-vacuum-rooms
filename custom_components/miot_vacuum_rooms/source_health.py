"""Hält die Quell-Entitäten gesund und meldet Probleme in den Reparaturen.

Die Quellen stehen als Registry-IDs in entry.data["sources"]. Legt Xiaomi
Home eine Entität neu an, zeigt die gespeicherte ID ins Leere. Die Heilung
sucht solche Rollen am Gerät neu (über die Endung, wie die Einrichtung).
Was danach fehlt oder deaktiviert ist, erscheint als Reparaturmeldung.
Beides läuft beim Laden und, entprellt, bei passenden Änderungen der
Entity-Registry.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.debounce import Debouncer

from .const import CONF_SOURCES, DOMAIN, OPTIONAL_ROLES, ROLES, SIID
from .discovery import find_sources, find_vacuum, role_label
from .util import parse_entity_suffix

_LOGGER = logging.getLogger(__name__)

# Ein Update von Xiaomi Home entfernt und erzeugt viele Entitäten kurz
# hintereinander; die Prüfung läuft CHECK_COOLDOWN Sekunden nach dem ersten
# Ereignis und danach höchstens einmal je CHECK_COOLDOWN Sekunden.
CHECK_COOLDOWN = 5

# Änderungen an einer Entität, die eine Prüfung auslösen
_RELEVANT_CHANGES = frozenset({"disabled_by", "entity_id", "device_id"})

ISSUE_MISSING_SOURCES = "missing_sources"
ISSUE_DISABLED_SOURCES = "disabled_sources"

# Pflichtrollen (Meldung, wenn sie fehlen) und alle Rollen
REQUIRED_ROLES: tuple[str, ...] = ("vacuum", *ROLES)
ALL_ROLES: tuple[str, ...] = (*REQUIRED_ROLES, *OPTIONAL_ROLES)


def issue_id(key: str, entry_id: str) -> str:
    return f"{key}_{entry_id}"


@callback
def async_find_device_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Xiaomi-Gerät des Eintrags: über die Vacuum-Quelle, sonst eine andere Quelle."""
    registry = er.async_get(hass)
    sources: dict[str, str] = entry.data[CONF_SOURCES]
    ordered = [sources.get("vacuum")] + [
        registry_id for role, registry_id in sources.items() if role != "vacuum"
    ]
    for registry_id in ordered:
        if registry_id is None:
            continue
        registry_entry = registry.async_get(registry_id)
        if registry_entry is not None and registry_entry.device_id is not None:
            return registry_entry.device_id
    return None


@callback
def async_heal_sources(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ersetzt fehlende oder tote Registry-IDs durch Funde am Gerät.

    Gültige Zuordnungen bleiben unangetastet. Die Vacuum-Quelle wird nur
    ersetzt, wenn am Gerät genau eine fremde Vacuum-Entität hängt; dann folgt
    auch entry.unique_id (die Duplikaterkennung des Config-Flows nutzt sie).
    Gibt zurück, ob der Eintrag geändert wurde.
    """
    registry = er.async_get(hass)
    sources: dict[str, str] = dict(entry.data[CONF_SOURCES])

    def valid(role: str) -> bool:
        registry_id = sources.get(role)
        return registry_id is not None and registry.async_get(registry_id) is not None

    if all(valid(role) for role in ALL_ROLES):
        return False
    device_id = async_find_device_id(hass, entry)
    if device_id is None:
        return False

    changed = False
    found, _ = find_sources(hass, device_id)
    for role, registry_id in found.items():
        if not valid(role):
            sources[role] = registry_id
            changed = True
    new_vacuum: str | None = None
    if not valid("vacuum"):
        new_vacuum = find_vacuum(hass, device_id)
        # Gehört die neue Vacuum-Entität schon einem anderen Eintrag (neu
        # eingerichtet, ohne den alten zu entfernen), bleibt sie fehlend.
        owner = (
            hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, new_vacuum)
            if new_vacuum is not None
            else None
        )
        if owner is not None and owner.entry_id != entry.entry_id:
            new_vacuum = None
        if new_vacuum is not None:
            sources["vacuum"] = new_vacuum
            changed = True
    if not changed:
        return False

    if new_vacuum is not None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SOURCES: sources}, unique_id=new_vacuum
        )
    else:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SOURCES: sources}
        )
    return True


@callback
def async_update_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Erzeugt oder löscht die Meldungen zu fehlenden und deaktivierten Quellen."""
    registry = er.async_get(hass)
    sources: dict[str, str] = entry.data[CONF_SOURCES]
    missing: list[str] = []
    disabled: list[str] = []
    for role in ALL_ROLES:
        registry_id = sources.get(role)
        registry_entry = registry.async_get(registry_id) if registry_id else None
        if registry_entry is None:
            if role in REQUIRED_ROLES:
                missing.append(role_label(role))
        elif registry_entry.disabled_by is not None:
            disabled.append(registry_entry.entity_id)

    _async_set_issue(
        hass, entry, ISSUE_MISSING_SOURCES, missing, ir.IssueSeverity.ERROR
    )
    _async_set_issue(
        hass, entry, ISSUE_DISABLED_SOURCES, disabled, ir.IssueSeverity.WARNING
    )


@callback
def _async_set_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    key: str,
    entities: list[str],
    severity: ir.IssueSeverity,
) -> None:
    if not entities:
        ir.async_delete_issue(hass, DOMAIN, issue_id(key, entry.entry_id))
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(key, entry.entry_id),
        is_fixable=False,
        severity=severity,
        translation_key=key,
        translation_placeholders={"title": entry.title, "entities": ", ".join(entities)},
    )


@callback
def async_delete_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Entfernt beide Meldungen eines Eintrags."""
    for key in (ISSUE_MISSING_SOURCES, ISSUE_DISABLED_SOURCES):
        ir.async_delete_issue(hass, DOMAIN, issue_id(key, entry_id))


@callback
def async_track_sources(hass: HomeAssistant, entry: ConfigEntry) -> CALLBACK_TYPE:
    """Prüft Quellen und Meldungen erneut, wenn sich die Entity-Registry ändert.

    Relevant ist eine Entität, die eine aktuelle Quelle ist (bei "remove" über
    ihre zuletzt bekannte Entitäts-ID), eine Endung _a_17_*/_p_17_* hat oder
    (bei "create"/"update") am bekannten Xiaomi-Gerät hängt. Ein "update"
    zählt nur, wenn disabled_by, entity_id oder device_id geändert wurde.
    Ändert die Heilung den Eintrag, lädt ihn der Update-Listener neu.
    Liefert die Funktion zum Abmelden.
    """
    registry = er.async_get(hass)
    source_entity_ids: set[str] = set()
    device_id: str | None = None

    @callback
    def _async_snapshot() -> None:
        """Merkt sich Entitäts-IDs der Quellen und das Gerät."""
        nonlocal device_id
        source_entity_ids.clear()
        for registry_id in entry.data[CONF_SOURCES].values():
            if (registry_entry := registry.async_get(registry_id)) is not None:
                source_entity_ids.add(registry_entry.entity_id)
        if (found := async_find_device_id(hass, entry)) is not None:
            device_id = found

    @callback
    def _async_check() -> None:
        async_heal_sources(hass, entry)
        async_update_issues(hass, entry)
        _async_snapshot()

    debouncer = Debouncer(
        hass,
        _LOGGER,
        cooldown=CHECK_COOLDOWN,
        immediate=False,
        function=_async_check,
    )

    @callback
    def _relevant(data: er.EventEntityRegistryUpdatedData) -> bool:
        action = data["action"]
        if action == "update" and not _RELEVANT_CHANGES & data["changes"].keys():
            return False
        entity_ids = {data["entity_id"], data.get("old_entity_id")}
        if source_entity_ids & entity_ids:
            return True
        parsed = parse_entity_suffix(data["entity_id"])
        if parsed is not None and parsed[1] == SIID:
            return True
        if action == "remove":
            return False
        registry_entry = registry.async_get(data["entity_id"])
        if registry_entry is None:
            return False
        if registry_entry.id in entry.data[CONF_SOURCES].values():
            return True
        return device_id is not None and registry_entry.device_id == device_id

    @callback
    def _async_registry_updated(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        if _relevant(event.data):
            debouncer.async_schedule_call()

    _async_snapshot()
    unsubscribe = hass.bus.async_listen(
        er.EVENT_ENTITY_REGISTRY_UPDATED, _async_registry_updated
    )

    @callback
    def _async_stop() -> None:
        unsubscribe()
        debouncer.async_shutdown()

    return _async_stop
