"""Data update coordinator for Netatmo Modular."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NetatmoApiClient, NetatmoApiError, NetatmoAuthError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class NetatmoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Netatmo data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_client: NetatmoApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config_entry = config_entry
        self.api = api_client
        self._homes: dict[str, dict[str, Any]] = {}
        self._rooms: dict[str, dict[str, Any]] = {}
        self._modules: dict[str, dict[str, Any]] = {}

    @property
    def homes(self) -> dict[str, dict[str, Any]]:
        """Get all homes."""
        return self._homes

    @property
    def rooms(self) -> dict[str, dict[str, Any]]:
        """Get all rooms."""
        return self._rooms

    @property
    def modules(self) -> dict[str, dict[str, Any]]:
        """Get all modules."""
        return self._modules

    def get_room(self, room_id: str) -> dict[str, Any] | None:
        """Get room by ID."""
        return self._rooms.get(room_id)

    def get_module(self, module_id: str) -> dict[str, Any] | None:
        """Get module by ID."""
        return self._modules.get(module_id)

    def get_home_for_room(self, room_id: str) -> dict[str, Any] | None:
        """Get home containing the specified room."""
        room = self._rooms.get(room_id)
        if room:
            return self._homes.get(room.get("home_id", ""))
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Netatmo API."""
        try:
            data = await self.api.async_get_full_data()
            await self._process_data(data)
            
            # Save updated tokens if they changed
            await self._save_tokens()
            
            return data

        except NetatmoAuthError as err:
            _LOGGER.error("Authentication error: %s", err)
            raise UpdateFailed(f"Authentication error: {err}") from err

        except NetatmoApiError as err:
            _LOGGER.error("API error: %s", err)
            raise UpdateFailed(f"API error: {err}") from err

        except Exception as err:
            _LOGGER.exception("Unexpected error fetching Netatmo data")
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _process_data(self, data: dict[str, Any]) -> None:
        """Process the fetched data into structured dictionaries."""
        # Debug log pour voir ce que l'API renvoie
        _LOGGER.debug("RAW DATA FROM API: %s", data)

        self._homes = {}
        self._rooms = {}
        self._modules = {}

        for home in data.get("homes", []):
            home_id = home.get("id")
            if not home_id:
                continue

            home_name = home.get("name", "Unknown Home")
            self._homes[home_id] = {
                "id": home_id,
                "name": home_name,
                "altitude": home.get("altitude"),
                "coordinates": home.get("coordinates"),
                "country": home.get("country"),
                "timezone": home.get("timezone"),
                "therm_setpoint_default_duration": home.get("therm_setpoint_default_duration"),
                "therm_mode": home.get("status", {}).get("therm_mode"),
                "rooms": [],
                "modules": [],
            }

            # Process rooms
            status_rooms = {r["id"]: r for r in home.get("status", {}).get("rooms", [])}
            
            for room in home.get("rooms", []):
                room_id = room.get("id")
                if not room_id:
                    continue

                # Merge room definition with status
                room_status = status_rooms.get(room_id, {})
                
                room_data = {
                    "id": room_id,
                    "home_id": home_id,
                    "home_name": home_name,
                    "name": room.get("name", f"Room {room_id}"),
                    "type": room.get("type"),
                    "module_ids": room.get("module_ids", []),
                    # Status data
                    "therm_measured_temperature": room_status.get("therm_measured_temperature"),
                    "therm_setpoint_temperature": room_status.get("therm_setpoint_temperature"),
                    "therm_setpoint_mode": room_status.get("therm_setpoint_mode"),
                    "therm_setpoint_start_time": room_status.get("therm_setpoint_start_time"),
                    "therm_setpoint_end_time": room_status.get("therm_setpoint_end_time"),
                    "heating_power_request": room_status.get("heating_power_request"),
                    "anticipating": room_status.get("anticipating"),
                    "open_window": room_status.get("open_window"),
                }

                self._rooms[room_id] = room_data
                self._homes[home_id]["rooms"].append(room_id)

            # Process modules
            status_modules = {m["id"]: m for m in home.get("status", {}).get("modules", [])}
            
            for module in home.get("modules", []):
                module_id = module.get("id")
                if not module_id:
                    continue

                # Merge module definition with status
                module_status = status_modules.get(module_id, {})

                module_data = {
                    "id": module_id,
                    "home_id": home_id,
                    "home_name": home_name,
                    "name": module.get("name", f"Module {module_id}"),
                    "type": module.get("type"),
                    "setup_date": module.get("setup_date"),
                    "modules_bridged": module.get("modules_bridged", []),
                    "room_id": module.get("room_id"),
                    # Status data
                    "boiler_status": module_status.get("boiler_status"),
                    "boiler_valve_comfort_boost": module_status.get("boiler_valve_comfort_boost"),
                    "battery_state": module_status.get("battery_state"),
                    "battery_level": module_status.get("battery_level"),
                    "rf_strength": module_status.get("rf_strength"),
                    "wifi_strength": module_status.get("wifi_strength"),
                    "reachable": module_status.get("reachable", True),
                    "firmware": module_status.get("firmware"),
                }

                self._modules[module_id] = module_data
                self._homes[home_id]["modules"].append(module_id)

        _LOGGER.debug(
            "Processed %d homes, %d rooms, %d modules",
            len(self._homes),
            len(self._rooms),
            len(self._modules),
        )

    async def _save_tokens(self) -> None:
        """Save updated tokens to config entry."""
        new_data = {
            **self.config_entry.data,
            "token": {
                "access_token": self.api.access_token,
                "refresh_token": self.api.refresh_token,
                "expires_at": self.api.token_expires_at.isoformat() if self.api.token_expires_at else None,
            },
        }

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=new_data,
        )

    async def async_set_room_mode(
        self,
        room_id: str,
        mode: str,
        temp: float | None = None,
    ) -> bool:
        """Set room thermostat mode using the new setstate API."""
        room = self.get_room(room_id)
        if not room:
            _LOGGER.error("Room %s not found", room_id)
            return False

        home_id = room["home_id"]

        # --- C'EST ICI QUE LA MAGIE OPÈRE ---
        # On utilise async_set_state qui a été ajouté dans api.py
        success = await self.api.async_set_state(
            home_id=home_id,
            room_id=room_id,
            mode=mode,
            temp=temp,
        )

        if success:
            # Refresh data
            await self.async_request_refresh()

        return success

    async def async_set_home_mode(self, home_id: str, mode: str) -> bool:
        """Set home thermostat mode."""
        success = await self.api.async_set_therm_mode(
            home_id=home_id,
            mode=mode,
        )

        if success:
            await self.async_request_refresh()

        return success