"""Eine Taste pro angelerntem Raum."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import MiotVacuumConfigEntry, VacuumController

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MiotVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    async_add_entities(
        RoomButton(controller, name, room_id)
        for name, room_id in controller.rooms.items()
    )


class RoomButton(ButtonEntity):
    """Startet die Reinigung genau dieses Raums."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "room"
    _attr_icon = "mdi:robot-vacuum"

    def __init__(self, controller: VacuumController, room: str, room_id: int) -> None:
        self._controller = controller
        self._room = room
        self._attr_translation_placeholders = {"room": room}
        self._attr_unique_id = f"{controller.entry.entry_id}_room_{room_id}"
        self._attr_device_info = controller.device_info

    async def async_press(self) -> None:
        await self._controller.async_clean_rooms([self._room])
