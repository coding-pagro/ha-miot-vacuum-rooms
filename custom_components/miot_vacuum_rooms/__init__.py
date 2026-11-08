"""MIoT Saugroboter Räume.

Ergänzt die offizielle Xiaomi-Home-Integration um Raumreinigung nach Namen,
Auswahlfelder für Modus, Saugleistung, Nässe, Durchgänge und Routenpräferenz
sowie Tasten pro Raum.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .controller import MiotVacuumConfigEntry, VacuumController
from .const import CONF_SOURCES, DOMAIN, ROLES
from .discovery import MissingSourcesError, NoDeviceError, discover_sources
from .services import async_register_services

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
    _async_add_new_sources(hass, entry)
    entry.runtime_data = VacuumController(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MiotVacuumConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_add_new_sources(hass: HomeAssistant, entry: MiotVacuumConfigEntry) -> None:
    """Ergänzt Rollen, die nach der Einrichtung dazugekommen sind (z. B. prop_task, prop_error).

    Gelingt die Suche nicht, bleibt alles wie es ist; die Steuerung kommt
    ohne die neue Rolle aus (Verhalten wie vorher).
    """
    sources: dict[str, str] = entry.data[CONF_SOURCES]
    if all(role in sources for role in ROLES):
        return
    vacuum = er.async_get(hass).async_get(sources["vacuum"])
    if vacuum is None:
        return
    try:
        found = discover_sources(hass, vacuum.entity_id)
    except (NoDeviceError, MissingSourcesError):
        return
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_SOURCES: {**found, **sources}}
    )


async def _async_options_updated(
    hass: HomeAssistant, entry: MiotVacuumConfigEntry
) -> None:
    """Lädt neu, damit die Tasten zu den Räumen passen."""
    await hass.config_entries.async_reload(entry.entry_id)
