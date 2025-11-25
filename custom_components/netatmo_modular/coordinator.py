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

        except NetatmoAuthError as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except NetatmoApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _process_data(self, data: dict[str, Any]) -> None:
        """Process the fetched data into structured dictionaries."""
        # Note: On ne clear pas brutalement pour éviter les scintillements,
        # on remplace au fur et à mesure.
        
        homes_list = data.get("homes", [])
        if not homes_list:
            return

        for home in homes_list:
            home_id = home.get("id")
            if not home_id:
                continue

            home_name = home.get("name", "Unknown Home")
            
            # Structure de base si pas existante
            if home_id not in self._homes:
                self._homes[home_id] = {
                    "id": home_id,
                    "name": home_name,
                    "rooms": [],
                    "modules": [],
                }
            
            # Mise à jour status global
            self._homes[home_id]["therm_mode"] = home.get("status", {}).get("therm_mode")

            status_rooms = {r["id"]: r for r in home.get("status", {}).get("rooms", [])}
            status_modules = {m["id"]: m for m in home.get("status", {}).get("modules", [])}

            # Process rooms
            for room in home.get("rooms", []):
                room_id = room.get("id")
                if not room_id:
                    continue

                room_status = status_rooms.get(room_id, {})
                
                # On met à jour ou on crée
                room_data = {
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
                self._rooms[room_id] = room_data
                
                if room_id not in self._homes[home_id]["rooms"]:
                    self._homes[home_id]["rooms"].append(room_id)

            # Process modules
            for module in home.get("modules", []):
                module_id = module.get("id")
                if not module_id:
                    continue

                module_status = status_modules.get(module_id, {})
                
                self._modules[module_id] = {
                    "id": module_id,
                    "home_id": home_id,
                    "name": module.get("name", f"Module {module_id}"),
                    "type": module.get("type"),
                    "battery_level": module_status.get("battery_level"),
                    "rf_strength": module_status.get("rf_strength"),
                    "wifi_strength": module_status.get("wifi_strength"),
                    "boiler_status": module_status.get("boiler_status"),
                    "reachable": module_status.get("reachable", True),
                }
                
                if module_id not in self._homes[home_id]["modules"]:
                    self._homes[home_id]["modules"].append(module_id)

    async def _save_tokens(self) -> None:
        """Save updated tokens to config entry."""
        new_token_data = {
            "access_token": self.api.access_token,
            "refresh_token": self.api.refresh_token,
            "expires_at": self.api.token_expires_at.isoformat() if self.api.token_expires_at else None,
        }
        
        if self.config_entry.data.get("token") != new_token_data:
            new_data = {**self.config_entry.data, "token": new_token_data}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)

    async def async_set_room_mode(
        self,
        room_id: str,
        mode: str,
        temp: float | None = None,
        fp: str | None = None,
    ) -> bool:
        """Set room thermostat mode with Optimistic UI update."""
        room = self.get_room(room_id)
        if not room:
            _LOGGER.error("Cannot set mode: Room %s not found", room_id)
            return False

        success = await self.api.async_set_state(
            home_id=room["home_id"],
            room_id=room_id,
            mode=mode,
            temp=temp,
            fp=fp,
        )

        if success:
            # --- OPTIMISATION : Mise à jour Optimiste (Immédiate) ---
            # On fait semblant que la valeur est déjà changée pour que l'UI réagisse instantanément
            # sans attendre le retour lent de l'API Netatmo.
            
            if room_id in self._rooms:
                if mode == "manual":
                    self._rooms[room_id]["therm_setpoint_mode"] = "manual"
                    # Si on a spécifié un Fil Pilote (ex: 'comfort', 'frost_guard'), on l'applique
                    if fp:
                        self._rooms[room_id]["therm_setpoint_fp"] = fp
                    # Si on a spécifié une température, on l'applique
                    if temp:
                        self._rooms[room_id]["therm_setpoint_temperature"] = temp
                else:
                    # Si on passe en 'home', 'schedule', 'away', 'frost_guard' (mode direct)
                    # Attention: si mode est 'home' (le preset Schedule), l'API renverra 'schedule'
                    if mode == "home":
                        self._rooms[room_id]["therm_setpoint_mode"] = "schedule"
                    else:
                        self._rooms[room_id]["therm_setpoint_mode"] = mode
            
            # On notifie Home Assistant que les données ont changé (même si c'est du fake temporaire)
            self.async_update_listeners()

            # Enfin, on lance le vrai rafraichissement pour se synchroniser plus tard
            await self.async_request_refresh()
        
        return success