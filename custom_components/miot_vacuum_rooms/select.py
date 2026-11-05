"""Auswahlfelder für Modus, Saugleistung, Nässe, Durchgänge und Route."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import SELECTS
from .controller import MiotVacuumConfigEntry, VacuumController

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MiotVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    async_add_entities(MiotVacuumSelect(controller, key) for key in SELECTS)


class MiotVacuumSelect(SelectEntity, RestoreEntity):
    """Zustand kommt vom Sensor des Roboters, Änderungen gehen als Befehl raus.

    Die Nässe hat keinen Sensor. Dort wird der zuletzt aus HA gesetzte Wert
    gemerkt; Änderungen in der App bleiben für HA unsichtbar.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: VacuumController, key: str) -> None:
        self._controller = controller
        self._key = key
        spec = SELECTS[key]
        self._sensor_role: str | None = spec["sensor"]
        self._from_sensor = {
            sensor_value: option
            for option, (_, sensor_value) in spec["options"].items()
            if sensor_value is not None
        }
        self._attr_translation_key = key
        self._attr_options = list(spec["options"])
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_device_info = controller.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._sensor_role is None:
            if (last := await self.async_get_last_state()) is not None:
                if last.state in self._attr_options:
                    self._attr_current_option = last.state
            return
        entity_id = self._controller.entity_id(self._sensor_role)
        if entity_id is None:
            return
        self._apply(self.hass.states.get(entity_id))
        self.async_on_remove(
            async_track_state_change_event(self.hass, [entity_id], self._changed)
        )

    @callback
    def _changed(self, event: Event) -> None:
        self._apply(event.data.get("new_state"))
        self.async_write_ha_state()

    def _apply(self, state: State | None) -> None:
        if state is None:
            self._attr_current_option = None
        else:
            self._attr_current_option = self._from_sensor.get(state.state)

    async def async_select_option(self, option: str) -> None:
        await self._controller.async_set_option(self._key, option)
        if self._sensor_role is None:
            self._attr_current_option = option
            self.async_write_ha_state()
