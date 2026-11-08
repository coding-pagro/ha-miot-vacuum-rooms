"""Einrichtung und Optionen."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    ATTR_NAME,
    ATTR_TIMEOUT,
    CONF_REQUIRE_DOCKED,
    CONF_ROOMS,
    CONF_SOURCES,
    CONF_VACUUM,
    DEFAULT_REQUIRE_DOCKED,
    DOMAIN,
    LEARN_TIMEOUT_DEFAULT,
)
from .discovery import MissingSourcesError, NoDeviceError, discover_sources
from .util import format_rooms_text, parse_rooms_text


class MiotVacuumRoomsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Auswahl des Saugroboters aus der Xiaomi-Home-Integration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MiotVacuumRoomsOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"missing": ""}
        if user_input is not None:
            entity_id = user_input[CONF_VACUUM]
            try:
                sources = discover_sources(self.hass, entity_id)
            except NoDeviceError:
                errors["base"] = "no_device"
            except MissingSourcesError as err:
                errors["base"] = "missing_entities"
                placeholders["missing"] = ", ".join(err.missing)
            else:
                await self.async_set_unique_id(sources["vacuum"])
                self._abort_if_unique_id_configured()
                state = self.hass.states.get(entity_id)
                return self.async_create_entry(
                    title=state.name if state else entity_id,
                    data={CONF_SOURCES: sources},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_VACUUM): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="vacuum")
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )


class MiotVacuumRoomsOptionsFlow(OptionsFlow):
    """Menü: Räume als Text pflegen oder einen Raum anlernen."""

    def __init__(self) -> None:
        self._learn_task: asyncio.Task[int] | None = None
        self._learn_name = ""
        self._learn_timeout = LEARN_TIMEOUT_DEFAULT
        self._learn_room_id = 0
        self._learn_error = "learn_failed"
        self._learn_placeholders: dict[str, str] = {}

    @callback
    def async_remove(self) -> None:
        """Bricht ein noch wartendes Anlernen ab, wenn der Dialog geschlossen wird."""
        self._discard_learn_task()

    def _discard_learn_task(self) -> None:
        task, self._learn_task = self._learn_task, None
        if task is not None and not task.done():
            task.cancel()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["rooms", "learn"])

    # --- Räume bearbeiten (wie bisher) ----------------------------------

    async def async_step_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"error": ""}
        if user_input is not None:
            try:
                rooms = parse_rooms_text(user_input.get(CONF_ROOMS, ""))
            except ValueError as err:
                errors[CONF_ROOMS] = "invalid_rooms"
                placeholders["error"] = str(err)
            else:
                return self.async_create_entry(
                    data={
                        CONF_ROOMS: rooms,
                        CONF_REQUIRE_DOCKED: user_input[CONF_REQUIRE_DOCKED],
                    }
                )

        options = self.config_entry.options
        suggested = user_input or {
            CONF_ROOMS: format_rooms_text(options.get(CONF_ROOMS, {})),
            CONF_REQUIRE_DOCKED: options.get(
                CONF_REQUIRE_DOCKED, DEFAULT_REQUIRE_DOCKED
            ),
        }
        schema = vol.Schema(
            {
                vol.Optional(CONF_ROOMS): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Required(
                    CONF_REQUIRE_DOCKED, default=DEFAULT_REQUIRE_DOCKED
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="rooms",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )

    # --- Raum anlernen ----------------------------------------------------

    async def async_step_learn(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="not_loaded")
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input.get(ATTR_NAME, "").strip()
            if not name:
                errors[ATTR_NAME] = "empty_name"
            else:
                self._learn_name = name
                self._learn_timeout = int(user_input[ATTR_TIMEOUT])
                self._discard_learn_task()
                return await self.async_step_learning()

        schema = vol.Schema(
            {
                vol.Required(ATTR_NAME): selector.TextSelector(),
                vol.Required(
                    ATTR_TIMEOUT, default=LEARN_TIMEOUT_DEFAULT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=300,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="learn",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._learn_task is None:
            controller = self.config_entry.runtime_data
            self._learn_task = self.hass.async_create_task(
                controller.async_learn_room(self._learn_name, self._learn_timeout)
            )
        task = self._learn_task
        if not task.done():
            return self.async_show_progress(
                step_id="learning",
                progress_action="learning",
                progress_task=task,
                description_placeholders={"room": self._learn_name},
            )

        # Erledigten Task verwerfen, sonst hält ein Wiederholen ihn für ein neues Ergebnis.
        self._learn_task = None
        if task.cancelled():
            self._learn_error = "learn_failed"
            self._learn_placeholders = {"error": ""}
            return self.async_show_progress_done(next_step_id="learn_failed")
        err = task.exception()
        if err is None:
            self._learn_room_id = task.result()
            return self.async_show_progress_done(next_step_id="learned")
        if not isinstance(err, HomeAssistantError):
            raise err
        key = err.translation_key
        if key in ("learn_timeout", "learn_not_single"):
            self._learn_error = key
            self._learn_placeholders = dict(err.translation_placeholders or {})
        else:
            self._learn_error = "learn_failed"
            self._learn_placeholders = {"error": str(err)}
        return self.async_show_progress_done(next_step_id="learn_failed")

    async def async_step_learned(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Der Raum ist schon gespeichert; die Optionen unverändert übernehmen.
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="learned",
            description_placeholders={
                "room": self._learn_name,
                "id": str(self._learn_room_id),
            },
        )

    async def async_step_learn_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_learn()
        return self.async_show_form(
            step_id="learn_failed",
            errors={"base": self._learn_error},
            description_placeholders={
                "error": "",
                "seconds": "",
                "ids": "",
                **self._learn_placeholders,
            },
        )
