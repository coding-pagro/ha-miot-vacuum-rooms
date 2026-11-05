"""Dienste der Integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ENTRY_ID,
    ATTR_NAME,
    ATTR_ROOMS,
    ATTR_TIMEOUT,
    DOMAIN,
    LEARN_TIMEOUT_DEFAULT,
    SERVICE_CLEAN_FLOOR,
    SERVICE_CLEAN_ROOMS,
    SERVICE_FORGET_ROOM,
    SERVICE_LEARN_ROOM,
)
from .controller import VacuumController

_ENTRY = {vol.Optional(ATTR_ENTRY_ID): cv.string}

CLEAN_ROOMS_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        vol.Required(ATTR_ROOMS): vol.All(
            cv.ensure_list, [cv.string], vol.Length(min=1)
        ),
    }
)
CLEAN_FLOOR_SCHEMA = vol.Schema({**_ENTRY})
LEARN_ROOM_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_TIMEOUT, default=LEARN_TIMEOUT_DEFAULT): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=300)
        ),
    }
)
FORGET_ROOM_SCHEMA = vol.Schema({**_ENTRY, vol.Required(ATTR_NAME): cv.string})


def _get_controller(hass: HomeAssistant, entry_id: str | None) -> VacuumController:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if entry_id is not None:
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_not_found"
        )
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entry"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_required"
        )
    return entries[0].runtime_data


def async_register_services(hass: HomeAssistant) -> None:
    """Registriert die Dienste einmalig beim Laden der Integration."""

    async def _clean_rooms(call: ServiceCall) -> None:
        controller = _get_controller(hass, call.data.get(ATTR_ENTRY_ID))
        await controller.async_clean_rooms(call.data[ATTR_ROOMS])

    async def _clean_floor(call: ServiceCall) -> None:
        controller = _get_controller(hass, call.data.get(ATTR_ENTRY_ID))
        await controller.async_clean_floor()

    async def _learn_room(call: ServiceCall) -> dict[str, str | int]:
        controller = _get_controller(hass, call.data.get(ATTR_ENTRY_ID))
        name = call.data[ATTR_NAME].strip()
        room_id = await controller.async_learn_room(name, call.data[ATTR_TIMEOUT])
        return {"room": name, "id": room_id}

    async def _forget_room(call: ServiceCall) -> None:
        controller = _get_controller(hass, call.data.get(ATTR_ENTRY_ID))
        controller.forget_room(call.data[ATTR_NAME].strip())

    hass.services.async_register(
        DOMAIN, SERVICE_CLEAN_ROOMS, _clean_rooms, schema=CLEAN_ROOMS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAN_FLOOR, _clean_floor, schema=CLEAN_FLOOR_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_ROOM,
        _learn_room,
        schema=LEARN_ROOM_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FORGET_ROOM, _forget_room, schema=FORGET_ROOM_SCHEMA
    )
