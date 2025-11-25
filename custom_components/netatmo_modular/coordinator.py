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
            await self._save_tokens()
            return data
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    async def _process_data(self, data: dict[str, Any]) -> None:
        """Process the fetched data into structured dictionaries."""
        self._homes.clear()
        self._rooms.clear()
        self._modules.clear()

        homes_list = data.get("homes", [])
        if not homes_list:
            return

        for home in homes_list:
            home_id = home.get("id")
            if not home_id:
                continue

            home_name = home.get("name", "Unknown Home")
            
            self._homes[home_id] = {
                "id": home_id,
                "name": home_name,
                "therm_mode": home.get("status", {}).get("therm_mode"),
                "rooms": [],
                "modules": [],
            }

            status_rooms = {r["id"]: r for r in home.get("status", {}).get("rooms", [])}
            status_modules = {m["id"]: m for m in home.get("status", {}).get("modules", [])}

            # Process rooms
            for room in home.get("rooms", []):
                room_id = room.get("id")
                if not room_id:
                    continue
                room_status = status_rooms.get(room_id, {})
                self._rooms[room_id] = {
                    "id": room_id,
                    "home_id": home_id,
                    "home_name": home_name,
                    "name": room.get("name", f"Room {room_id}"),
                    "type": room.get("type"),
                    "module_ids": room.get("module_ids", []),
                    "therm_measured_temperature": room_status.get("therm_measured_temperature"),
                    "therm_setpoint_temperature": room_status.get("therm_setpoint_temperature"),
                    "therm_setpoint_mode": room_status.get("therm_setpoint_mode"),
                    "therm_setpoint_fp": room_status.get("therm_setpoint_fp"),
                    "heating_power_request": room_status.get("heating_power_request"),
                    "anticipating": room_status.get("anticipating"),
                    "open_window": room_status.get("open_window"),
                }
                self._homes[home_id]["rooms"].append(room_id)

            # Process modules
            for module in home.get("modules", []):
                module_id = module.get("id")
                module_type = module.get("type")
                
                if not module_id:
                    continue
                
                module_status = status_modules.get(module_id, {})
                
                self._modules[module_id] = {
                    "id": module_id,
                    "home_id": home_id,
                    "name": module.get("name", f"Module {module_id}"),
                    "type": module_type,
                    "bridge": module.get("bridge"), # <--- CAPTURE DU PONT (CRITIQUE)
                    "battery_level": module_status.get("battery_level"),
                    "rf_strength": module_status.get("rf_strength"),
                    "wifi_strength": module_status.get("wifi_strength"),
                    "boiler_status": module_status.get("boiler_status"),
                    "reachable": module_status.get("reachable", True),
                    "on": module_status.get("on"),
                    "brightness": module_status.get("brightness"),
                    "power": module_status.get("power"),
                }
                self._homes[home_id]["modules"].append(module_id)

    async def _save_tokens(self) -> None:
        """Save updated tokens."""
        new_token = {
            "access_token": self.api.access_token,
            "refresh_token": self.api.refresh_token,
            "expires_at": self.api.token_expires_at.isoformat() if self.api.token_expires_at else None,
        }
        if self.config_entry.data.get("token") != new_token:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, "token": new_token}
            )

    async def async_set_room_mode(self, room_id: str, mode: str, temp: float = None, fp: str = None) -> bool:
        room = self.get_room(room_id)
        if not room: return False
        success = await self.api.async_set_state(room["home_id"], room_id, mode, temp, fp)
        if success: 
            if mode == "manual":
                self._rooms[room_id]["therm_setpoint_mode"] = "manual"
                if fp: self._rooms[room_id]["therm_setpoint_fp"] = fp
            elif mode == "home":
                self._rooms[room_id]["therm_setpoint_mode"] = "schedule"
            else:
                self._rooms[room_id]["therm_setpoint_mode"] = mode
            self.async_update_listeners()
            await self.async_request_refresh()
        return success

    async def async_set_light_state(self, module_id: str, on: bool = None, brightness: int = None) -> bool:
        """Set light state with optimistic update."""
        module = self.get_module(module_id)
        if not module: return False

        # On passe le paramètre bridge si disponible
        success = await self.api.async_set_module_state(
            home_id=module["home_id"], 
            module_id=module_id, 
            on=on, 
            brightness=brightness,
            bridge_id=module.get("bridge") # <--- ENVOI DU PONT A L'API
        )
        
        if success:
            if on is not None:
                self._modules[module_id]["on"] = on
            if brightness is not None:
                self._modules[module_id]["brightness"] = brightness
            
            self.async_update_listeners()
            await self.async_request_refresh()
        
        return success