"""Einrichtung und Optionen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_REQUIRE_DOCKED,
    CONF_ROOMS,
    CONF_SOURCES,
    CONF_VACUUM,
    DEFAULT_REQUIRE_DOCKED,
    DOMAIN,
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
    """Räume als Text pflegen und Startbedingung wählen."""

    async def async_step_init(
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
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )
