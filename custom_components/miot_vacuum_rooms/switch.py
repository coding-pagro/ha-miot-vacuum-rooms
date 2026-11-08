"""Schalter: Raumeinstellungen der App verwenden (Modus Personalisieren) oder nicht."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .controller import MiotVacuumConfigEntry, VacuumController

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MiotVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([RoomSettingsSwitch(entry.runtime_data)])


class RoomSettingsSwitch(SwitchEntity, RestoreEntity):
    """An: Raumreinigung im Modus Personalisieren. Aus: globaler Modus bleibt."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "use_app_room_settings"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tune-variant"

    def __init__(self, controller: VacuumController) -> None:
        self._controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_use_app_room_settings"
        self._attr_device_info = controller.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._controller.use_app_room_settings = last.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self._controller.use_app_room_settings

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._controller.use_app_room_settings = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._controller.use_app_room_settings = False
        self.async_write_ha_state()
