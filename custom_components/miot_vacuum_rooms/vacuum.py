"""Eigene Saugroboter-Entität: sicherer Start, Saugleistung, Reinigung nach Bereichen."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    Segment,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, MODE_CUSTOM, SELECTS
from .controller import MiotVacuumConfigEntry, VacuumController

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

_ACTIVITIES = {
    activity.value: activity
    for activity in (
        VacuumActivity.CLEANING,
        VacuumActivity.DOCKED,
        VacuumActivity.IDLE,
        VacuumActivity.PAUSED,
        VacuumActivity.RETURNING,
        VacuumActivity.ERROR,
    )
}
_UNAVAILABLE = (None, "unknown", "unavailable")
# Zustände der Quelle, in denen ein Auftrag läuft
_RUNNING = ("cleaning", "paused")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MiotVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MiotRoomsVacuum(entry.runtime_data)])


class MiotRoomsVacuum(StateVacuumEntity):
    """Spiegelt den Xiaomi-Saugroboter und startet nur mit Raumauswahl."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_translation_key = "vacuum"
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.CLEAN_AREA
    )

    def __init__(self, controller: VacuumController) -> None:
        self._controller = controller
        fan = SELECTS["fan"]["options"]
        self._attr_fan_speed_list = list(fan)
        self._fan_from_sensor = {sensor: option for option, (_, sensor) in fan.items()}
        self._attr_unique_id = f"{controller.entry.entry_id}_vacuum"
        self._attr_device_info = controller.device_info
        self._logged_states: set[str] = set()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._async_check_segments_changed()
        tracked = [
            entity_id
            for role in ("vacuum", "prop_fan")
            if (entity_id := self._controller.entity_id(role)) is not None
        ]
        self._update()
        if tracked:
            self.async_on_remove(
                async_track_state_change_event(self.hass, tracked, self._changed)
            )

    # --- Zustand ---------------------------------------------------------

    @callback
    def _changed(self, event: Event) -> None:
        self._update()
        self.async_write_ha_state()

    def _update(self) -> None:
        state = self._controller.state("vacuum")
        self._attr_available = state not in _UNAVAILABLE
        self._attr_activity = _ACTIVITIES.get(state) if state else None
        if state not in _UNAVAILABLE and state not in _ACTIVITIES:
            if state not in self._logged_states:
                self._logged_states.add(state)
                _LOGGER.debug("Unbekannter Zustand des Saugroboters: %s", state)
        self._attr_fan_speed = self._fan_from_sensor.get(
            self._controller.state("prop_fan")
        )

    # --- Steuerung -------------------------------------------------------

    async def async_start(self) -> None:
        """Pausiert: fortsetzen. Sonst alle angelernten Räume reinigen."""
        if self._controller.state("vacuum") == VacuumActivity.PAUSED:
            await self._controller.async_vacuum_command("start")
            return
        rooms = list(self._controller.rooms)
        if not rooms:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_rooms"
            )
        await self._controller.async_clean_rooms(rooms)

    async def async_pause(self) -> None:
        await self._controller.async_vacuum_command("pause")

    async def async_stop(self, **kwargs: Any) -> None:
        await self._controller.async_vacuum_command("stop")

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self._controller.async_vacuum_command("return_to_base")

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Setzt die globale Saugleistung (nicht die Raumeinstellung der App)."""
        if fan_speed not in self._attr_fan_speed_list:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_fan_speed",
                translation_placeholders={
                    "fan_speed": fan_speed,
                    "options": ", ".join(self._attr_fan_speed_list),
                },
            )
        custom = SELECTS["mode"]["options"][MODE_CUSTOM][1]
        if (
            self._controller.state("vacuum") in _RUNNING
            and self._controller.state("prop_mode") == custom
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="fan_speed_customised"
            )
        await self._controller.async_set_option("fan", fan_speed)

    # --- Bereiche --------------------------------------------------------

    def _segments(self) -> list[Segment]:
        return [
            Segment(id=str(room_id), name=name)
            for name, room_id in self._controller.rooms.items()
        ]

    async def async_get_segments(self) -> list[Segment]:
        return self._segments()

    async def async_clean_segments(self, segment_ids: list[str], **kwargs: Any) -> None:
        """Reinigt die Räume zu den Segmenten, Reihenfolge bleibt erhalten."""
        names_by_id = {str(room_id): name for name, room_id in self._controller.rooms.items()}
        names: list[str] = []
        for segment_id in segment_ids:
            if (name := names_by_id.get(segment_id)) is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unknown_segment",
                    translation_placeholders={"segment": segment_id},
                )
            names.append(name)
        await self._controller.async_clean_rooms(names)

    @callback
    def _async_check_segments_changed(self) -> None:
        """Meldet geänderte Raum-IDs, damit die Bereiche neu zugeordnet werden.

        Verglichen werden nur die IDs: die Zuordnung hängt an der ID, eine
        Umbenennung lässt sie gültig.
        """
        if self.registry_entry is None:
            return
        last_seen = self.last_seen_segments
        if last_seen is None:
            return
        current = {segment.id for segment in self._segments()}
        if {segment.id for segment in last_seen} != current:
            self.async_create_segments_issue()
