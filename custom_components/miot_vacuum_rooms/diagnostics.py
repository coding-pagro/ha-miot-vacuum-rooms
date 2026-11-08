"""Diagnose-Datei für Fehlerberichte.

Entitäts-IDs von Xiaomi Home enthalten die numerische Geräte-ID; sie wird
geschwärzt. Registry-IDs, device_ids und Geräte-Identifikatoren erscheinen
nicht.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_REQUIRE_DOCKED,
    CONF_ROOMS,
    CONF_SOURCES,
    DEFAULT_REQUIRE_DOCKED,
    DOMAIN,
)
from .source_health import (
    ALL_ROLES,
    ISSUE_DISABLED_SOURCES,
    ISSUE_MISSING_SOURCES,
    async_find_device_id,
    issue_id,
)
from .util import redact_entity_id


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Zustand des Eintrags, seiner Quellen und des Xiaomi-Geräts."""
    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "options": {
                CONF_ROOMS: dict(entry.options.get(CONF_ROOMS, {})),
                CONF_REQUIRE_DOCKED: entry.options.get(
                    CONF_REQUIRE_DOCKED, DEFAULT_REQUIRE_DOCKED
                ),
            },
        },
        "sources": _sources(hass, entry),
        "controller": _controller(entry),
        "device": _device(hass, entry),
        "issues": {
            key: ir.async_get(hass).async_get_issue(
                DOMAIN, issue_id(key, entry.entry_id)
            )
            is not None
            for key in (ISSUE_MISSING_SOURCES, ISSUE_DISABLED_SOURCES)
        },
    }


def _sources(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    registry = er.async_get(hass)
    sources: dict[str, str] = entry.data[CONF_SOURCES]
    result: dict[str, dict[str, Any]] = {}
    for role in ALL_ROLES:
        registry_id = sources.get(role)
        registry_entry = registry.async_get(registry_id) if registry_id else None
        if registry_entry is None:
            result[role] = {
                "entity_id": None,
                "state": None,
                "disabled": False,
                "missing": True,
            }
            continue
        state = hass.states.get(registry_entry.entity_id)
        result[role] = {
            "entity_id": redact_entity_id(registry_entry.entity_id),
            "state": state.state if state else None,
            "disabled": registry_entry.disabled_by is not None,
            "missing": False,
        }
    return result


def _controller(entry: ConfigEntry) -> dict[str, Any] | None:
    controller = getattr(entry, "runtime_data", None)
    if controller is None:
        return None
    problem = controller.problem
    return {
        "use_app_room_settings": controller.use_app_room_settings,
        "job_pending": controller.job_pending,
        "job_paused": controller.job_paused,
        "problem": (
            None
            if problem is None
            else {
                "key": problem[0],
                "robot_error_code": problem[1],
                "station_error_code": problem[2],
            }
        ),
    }


def _device(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any] | None:
    device_id = async_find_device_id(hass, entry)
    device = dr.async_get(hass).async_get(device_id) if device_id else None
    if device is None:
        return None
    return {
        "manufacturer": device.manufacturer,
        "model": device.model,
        "sw_version": device.sw_version,
        "hw_version": device.hw_version,
    }
