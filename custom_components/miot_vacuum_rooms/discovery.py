"""Findet die Entitäten der Xiaomi-Home-Integration, die zum Saugroboter gehören.

Die Entitäten tragen die MIoT-Nummern am Ende der Entitäts-ID, zum Beispiel
notify.<gerät>_start_clean_a_17_1 (Aktion 1 von Dienst 17) oder
sensor.<gerät>_fan_mode_p_17_13 (Eigenschaft 13 von Dienst 17).
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import OPTIONAL_ROLES, ROLES, SIID
from .util import parse_entity_suffix

_DOMAIN_FOR_KIND = {"a": "notify", "p": "sensor"}


class NoDeviceError(Exception):
    """Die gewählte Entität gehört zu keinem Gerät."""


class MissingSourcesError(Exception):
    """Am Gerät fehlen erwartete Entitäten."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        self.missing = missing


def discover_sources(hass: HomeAssistant, vacuum_entity_id: str) -> dict[str, str]:
    """Liefert Rolle -> Registry-ID, inklusive der Rolle "vacuum".

    Optionale Rollen sind nur enthalten, wenn das Gerät sie hat. Deaktivierte
    Entitäten zählen mit (sie können später aktiviert werden).
    """
    registry = er.async_get(hass)
    vacuum = registry.async_get(vacuum_entity_id)
    if vacuum is None or vacuum.device_id is None:
        raise NoDeviceError(vacuum_entity_id)

    found: dict[tuple[str, str, int], str] = {}
    for entry in er.async_entries_for_device(
        registry, vacuum.device_id, include_disabled_entities=True
    ):
        parsed = parse_entity_suffix(entry.entity_id)
        if parsed is None:
            continue
        kind, siid, number = parsed
        if siid != SIID:
            continue
        found.setdefault((entry.domain, kind, number), entry.id)

    sources = {"vacuum": vacuum.id}
    missing: list[str] = []
    for role, (kind, number) in ROLES.items():
        domain = _DOMAIN_FOR_KIND[kind]
        registry_id = found.get((domain, kind, number))
        if registry_id is None:
            missing.append(f"{domain} {kind}_{SIID}_{number}")
        else:
            sources[role] = registry_id
    if missing:
        raise MissingSourcesError(missing)
    for role, key in OPTIONAL_ROLES.items():
        if (registry_id := found.get(key)) is not None:
            sources[role] = registry_id
    return sources
