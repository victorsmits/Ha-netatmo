"""Data update coordinator."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NetatmoApiClient
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class NetatmoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Netatmo data via Pyatmo."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api_client: NetatmoApiClient,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config_entry = config_entry
        self.api = api_client
        self.homes = {} # Pyatmo Home objects

    async def _async_update_data(self) -> dict:
        """Fetch data."""
        try:
            await self.api.async_update_data()
            self.homes = self.api.account.homes
            return self.homes
        except Exception as err:
            raise UpdateFailed(f"Error updating Netatmo data: {err}") from err

    async def async_handle_webhook(self, data: dict[str, Any]) -> None:
        """Handle webhook."""
        _LOGGER.debug("Webhook received: %s", data)
        # On force le refresh pour mettre à jour les objets Pyatmo
        await self.async_request_refresh()

    # --- Commandes simplifiées (Pyatmo gère le Bridge !) ---

    async def async_set_light_state(self, home_id: str, module_id: str, on: bool = None, brightness: int = None) -> bool:
        """Set light state."""
        home = self.homes.get(home_id)
        if not home: return False

        data = {"modules": [{"id": module_id}]}
        if on is not None: data["modules"][0]["on"] = on
        if brightness is not None: data["modules"][0]["brightness"] = brightness

        # Pyatmo va automatiquement ajouter le bridge_id s'il est connu dans la topologie
        try:
            await home.async_set_state(data)
            await self.async_request_refresh() # Optimistic via refresh rapide
            return True
        except Exception as err:
            _LOGGER.error("Error setting light state: %s", err)
            return False

    async def async_set_room_mode(self, home_id: str, room_id: str, mode: str, temp: float = None, fp: str = None) -> bool:
        """Set room mode."""
        home = self.homes.get(home_id)
        if not home: return False

        room_data = {"id": room_id, "therm_setpoint_mode": mode}
        if temp: room_data["therm_setpoint_temperature"] = temp
        if fp: room_data["therm_setpoint_fp"] = fp

        try:
            await home.async_set_state({"rooms": [room_data]})
            await self.async_request_refresh()
            return True
        except Exception as err:
            _LOGGER.error("Error setting room mode: %s", err)
            return False