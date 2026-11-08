"""MIoT Saugroboter Räume.

Ergänzt die offizielle Xiaomi-Home-Integration um Raumreinigung nach Namen,
Auswahlfelder für Modus, Saugleistung, Nässe, Durchgänge und Routenpräferenz
sowie Tasten pro Raum.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .controller import MiotVacuumConfigEntry, VacuumController
from .services import async_register_services
from .source_health import (
    async_delete_issues,
    async_heal_sources,
    async_track_sources,
    async_update_issues,
)

PLATFORMS = [
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.VACUUM,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Registriert die Dienste, unabhängig von Konfigurationseinträgen."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MiotVacuumConfigEntry) -> bool:
    # Tote oder neue Quellen am Gerät suchen (z. B. nach einem Update von
    # Xiaomi Home oder für Rollen, die nach der Einrichtung dazukamen).
    async_heal_sources(hass, entry)
    async_update_issues(hass, entry)
    entry.runtime_data = VacuumController(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(async_track_sources(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MiotVacuumConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MiotVacuumConfigEntry) -> None:
    """Entfernt die Reparaturmeldungen des Eintrags."""
    async_delete_issues(hass, entry.entry_id)


async def _async_options_updated(
    hass: HomeAssistant, entry: MiotVacuumConfigEntry
) -> None:
    """Lädt neu, damit die Tasten zu den Räumen passen."""
    await hass.config_entries.async_reload(entry.entry_id)
