"""Findet die Entitäten der Xiaomi-Home-Integration, die zum Saugroboter gehören.

Die Entitäten tragen die MIoT-Nummern am Ende der Entitäts-ID, zum Beispiel
notify.<gerät>_start_clean_a_17_1 (Aktion 1 von Dienst 17) oder
sensor.<gerät>_fan_mode_p_17_13 (Eigenschaft 13 von Dienst 17).
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, OPTIONAL_ROLES, ROLES, SIID
from .util import parse_entity_suffix

_DOMAIN_FOR_KIND = {"a": "notify", "p": "sensor"}


class NoDeviceError(Exception):
    """Die gewählte Entität gehört zu keinem Gerät."""


class MissingSourcesError(Exception):
    """Am Gerät fehlen erwartete Entitäten."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        self.missing = missing


def role_label(role: str) -> str:
    """Lesbare Bezeichnung einer Rolle, z. B. 'notify a_17_1' oder 'vacuum'."""
    if role in ROLES:
        kind, number = ROLES[role]
        return f"{_DOMAIN_FOR_KIND[kind]} {kind}_{SIID}_{number}"
    if role in OPTIONAL_ROLES:
        domain, kind, number = OPTIONAL_ROLES[role]
        return f"{domain} {kind}_{SIID}_{number}"
    return role


def find_sources(
    hass: HomeAssistant, device_id: str
) -> tuple[dict[str, str], list[str]]:
    """Sucht die Rollen am Gerät, ohne die Rolle "vacuum".

    Liefert Rolle -> Registry-ID für alle gefundenen Pflicht- und optionalen
    Rollen und die fehlenden Pflichtrollen (Format wie MissingSourcesError).
    Deaktivierte Entitäten zählen mit (sie können später aktiviert werden).
    Haben mehrere Entitäten dieselbe Endung, gewinnt der erste Fund.
    """
    registry = er.async_get(hass)
    found: dict[tuple[str, str, int], str] = {}
    for entry in er.async_entries_for_device(
        registry, device_id, include_disabled_entities=True
    ):
        parsed = parse_entity_suffix(entry.entity_id)
        if parsed is None:
            continue
        kind, siid, number = parsed
        if siid != SIID:
            continue
        found.setdefault((entry.domain, kind, number), entry.id)

    sources: dict[str, str] = {}
    missing: list[str] = []
    for role, (kind, number) in ROLES.items():
        registry_id = found.get((_DOMAIN_FOR_KIND[kind], kind, number))
        if registry_id is None:
            missing.append(role_label(role))
        else:
            sources[role] = registry_id
    for role, key in OPTIONAL_ROLES.items():
        if (registry_id := found.get(key)) is not None:
            sources[role] = registry_id
    return sources, missing


def find_vacuum(hass: HomeAssistant, device_id: str) -> str | None:
    """Registry-ID der einzigen Vacuum-Entität am Gerät (ohne die eigenen).

    Gibt None zurück, wenn es keine oder mehrere gibt.
    """
    candidates = [
        entry.id
        for entry in er.async_entries_for_device(
            er.async_get(hass), device_id, include_disabled_entities=True
        )
        if entry.domain == Platform.VACUUM and entry.platform != DOMAIN
    ]
    return candidates[0] if len(candidates) == 1 else None


def discover_sources(hass: HomeAssistant, vacuum_entity_id: str) -> dict[str, str]:
    """Liefert Rolle -> Registry-ID, inklusive der Rolle "vacuum".

    Optionale Rollen sind nur enthalten, wenn das Gerät sie hat. Deaktivierte
    Entitäten zählen mit (sie können später aktiviert werden).
    """
    registry = er.async_get(hass)
    vacuum = registry.async_get(vacuum_entity_id)
    if vacuum is None or vacuum.device_id is None:
        raise NoDeviceError(vacuum_entity_id)

    found, missing = find_sources(hass, vacuum.device_id)
    if missing:
        raise MissingSourcesError(missing)
    return {"vacuum": vacuum.id, **found}
