"""Steuerlogik: übersetzt Aktionen in Befehle der Xiaomi-Home-Integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CLEAN_TYPE_AREA,
    CLEAN_TYPE_FULL,
    CONF_REQUIRE_DOCKED,
    CONF_ROOMS,
    CONF_SOURCES,
    DEFAULT_REQUIRE_DOCKED,
    DOMAIN,
    MODE_CUSTOM,
    SELECTS,
    WAIT_MODE_SECONDS,
)
from .util import (
    build_start_message,
    build_value_message,
    parse_clean_values,
    resolve_room_ids,
)

type MiotVacuumConfigEntry = ConfigEntry[VacuumController]

_UNAVAILABLE = (None, "unknown", "unavailable")


async def async_wait_for_state(
    hass: HomeAssistant,
    entity_id: str,
    predicate: Callable[[str], bool],
    timeout: float,
    *,
    check_current: bool = True,
) -> str | None:
    """Wartet, bis der Zustand der Entität das Prädikat erfüllt.

    Gibt den passenden Zustand zurück oder None bei Zeitüberschreitung.
    Mit check_current=False zählen nur neue Zustandswechsel.
    """
    future: asyncio.Future[str] = hass.loop.create_future()

    @callback
    def _changed(event: Event) -> None:
        new_state = event.data.get("new_state")
        if (
            new_state is not None
            and predicate(new_state.state)
            and not future.done()
        ):
            future.set_result(new_state.state)

    unsub = async_track_state_change_event(hass, [entity_id], _changed)
    try:
        if check_current:
            current = hass.states.get(entity_id)
            if current is not None and predicate(current.state):
                return current.state
        async with asyncio.timeout(timeout):
            return await future
    except TimeoutError:
        return None
    finally:
        unsub()


class VacuumController:
    """Kapselt alle Befehle an einen Saugroboter."""

    def __init__(self, hass: HomeAssistant, entry: MiotVacuumConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Xiaomi Home (MIoT)",
            model="Vacuum Rooms",
            entry_type=DeviceEntryType.SERVICE,
        )

    # --- Konfiguration -------------------------------------------------

    @property
    def rooms(self) -> dict[str, int]:
        raw = self.entry.options.get(CONF_ROOMS, {})
        return {str(name): int(room_id) for name, room_id in raw.items()}

    @property
    def require_docked(self) -> bool:
        return bool(
            self.entry.options.get(CONF_REQUIRE_DOCKED, DEFAULT_REQUIRE_DOCKED)
        )

    # --- Zugriff auf die Quell-Entitäten --------------------------------

    def entity_id(self, role: str) -> str | None:
        """Aktuelle Entitäts-ID einer Rolle (folgt Umbenennungen)."""
        registry_id = self.entry.data[CONF_SOURCES].get(role)
        if registry_id is None:
            return None
        registry_entry = er.async_get(self.hass).async_get(registry_id)
        return registry_entry.entity_id if registry_entry else None

    def _require_entity_id(self, role: str) -> str:
        entity_id = self.entity_id(role)
        if entity_id is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="source_missing",
                translation_placeholders={"role": role},
            )
        return entity_id

    def state(self, role: str) -> str | None:
        entity_id = self.entity_id(role)
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        return state.state if state else None

    # --- Befehle --------------------------------------------------------

    async def async_send(self, role: str, message: str) -> None:
        """Schickt eine Nachricht an eine notify-Entität der Xiaomi-Integration."""
        await self.hass.services.async_call(
            "notify",
            "send_message",
            {"entity_id": self._require_entity_id(role), "message": message},
            blocking=True,
        )

    async def async_vacuum_command(self, service: str) -> None:
        """Reicht start, pause, stop oder return_to_base an den Quell-Roboter durch."""
        await self.hass.services.async_call(
            "vacuum",
            service,
            {"entity_id": self._require_entity_id("vacuum")},
            blocking=True,
        )

    async def async_set_option(self, key: str, option: str) -> None:
        """Setzt Modus, Saugleistung, Nässe, Durchgänge oder Routenpräferenz."""
        spec = SELECTS[key]
        value = spec["options"][option][0]
        await self.async_send(spec["action"], build_value_message(value))

    def _check_ready(self) -> None:
        state = self.state("vacuum")
        if state in _UNAVAILABLE:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="vacuum_unavailable"
            )
        if self.require_docked and state != "docked":
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_docked",
                translation_placeholders={"state": str(state)},
            )

    async def _async_ensure_custom_mode(self) -> None:
        target = SELECTS["mode"]["options"][MODE_CUSTOM][1]
        if self.state("prop_mode") == target:
            return
        await self.async_set_option("mode", MODE_CUSTOM)
        reached = await async_wait_for_state(
            self.hass,
            self._require_entity_id("prop_mode"),
            lambda value: value == target,
            WAIT_MODE_SECONDS,
        )
        if reached is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="mode_timeout"
            )

    async def async_clean_rooms(self, names: list[str]) -> None:
        """Startet die Reinigung der genannten Räume (Modus: Personalisieren).

        Die Reihenfolge der Namen bestimmt die Reihenfolge der IDs in der Liste.
        """
        try:
            room_ids = resolve_room_ids(self.rooms, names)
        except KeyError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_room",
                translation_placeholders={"room": str(err.args[0])},
            ) from err
        self._check_ready()
        await self._async_ensure_custom_mode()
        await self.async_send(
            "act_start", build_start_message(CLEAN_TYPE_AREA, room_ids)
        )

    async def async_clean_floor(self) -> None:
        """Startet eine Reinigung des ganzen Stockwerks.

        UNGETESTET: Die Nachricht [1, "[]"] ist aus dem Zustand abgeleitet,
        den die App beim Start meldet (Full Clean, clean-values = []).
        """
        self._check_ready()
        await self.async_send("act_start", build_start_message(CLEAN_TYPE_FULL))

    # --- Räume anlernen -------------------------------------------------

    def _store_rooms(self, rooms: dict[str, int]) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_ROOMS: rooms}
        )

    async def async_learn_room(self, name: str, timeout: float) -> int:
        """Wartet auf einen in der App gestarteten Raum und speichert dessen ID."""
        name = name.strip()
        if not name:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="empty_name"
            )
        values_entity = self._require_entity_id("prop_values")
        reached = await async_wait_for_state(
            self.hass,
            values_entity,
            lambda value: bool(parse_clean_values(value)),
            timeout,
            check_current=False,
        )
        if reached is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="learn_timeout",
                translation_placeholders={"seconds": str(int(timeout))},
            )
        room_ids = parse_clean_values(reached) or []
        if len(room_ids) != 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="learn_not_single",
                translation_placeholders={"ids": reached},
            )
        room_id = room_ids[0]
        # Pro ID genau ein Name: ein älterer Name für dieselbe ID wird ersetzt.
        rooms = {n: i for n, i in self.rooms.items() if i != room_id and n != name}
        rooms[name] = room_id
        self._store_rooms(rooms)
        return room_id

    def forget_room(self, name: str) -> None:
        rooms = self.rooms
        if name not in rooms:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_room",
                translation_placeholders={"room": name},
            )
        del rooms[name]
        self._store_rooms(rooms)
