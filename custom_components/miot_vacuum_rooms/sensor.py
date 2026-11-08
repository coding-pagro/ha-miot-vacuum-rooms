"""Problemsensor: Fehlercodes von Roboter und Station als übersetzter Text."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import PROBLEM_OPTIONS
from .controller import MiotVacuumConfigEntry, VacuumController

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MiotVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([ProblemSensor(entry.runtime_data)])


class ProblemSensor(SensorEntity):
    """"none" ohne Fehler, sonst der übersetzte Text zum Fehlercode."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "problem"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PROBLEM_OPTIONS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller: VacuumController) -> None:
        self._controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_problem"
        self._attr_device_info = controller.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._update()
        tracked = [
            entity_id
            for role in ("prop_error", "prop_station_error")
            if (entity_id := self._controller.entity_id(role)) is not None
        ]
        if tracked:
            self.async_on_remove(
                async_track_state_change_event(self.hass, tracked, self._changed)
            )

    @callback
    def _changed(self, event: Event) -> None:
        self._update()
        self.async_write_ha_state()

    def _update(self) -> None:
        problem = self._controller.problem
        self._attr_available = problem is not None
        if problem is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        key, robot, station = problem
        self._attr_native_value = key
        self._attr_extra_state_attributes = {
            "robot_error_code": robot,
            "station_error_code": station,
        }
