"""Data update coordinator for Netatmo Modular."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyatmo import AsyncAccount

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class NetatmoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Netatmo data via Pyatmo."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        account: AsyncAccount,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config_entry = config_entry
        self.account = account
        self.homes: dict = {}

    async def _async_update_data(self) -> dict:
        """Fetch data from Netatmo API."""
        try:
            # Pyatmo v8+ : update_topology récupère maisons/pièces/modules
            await self.account.async_update_topology()
            # update_status récupère les états (températures, vannes, etc)
            await self.account.async_update_status()
            
            # On stocke les données brutes pyatmo ou on les structure
            self.homes = self.account.homes
            return self.homes
            
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    # Helpers pour accéder aux données Pyatmo facilement depuis les entités
    def get_room(self, room_id: str):
        for home in self.homes.values():
            if room_id in home.rooms:
                return home.rooms[room_id]
        return None

    def get_module(self, module_id: str):
        for home in self.homes.values():
            if module_id in home.modules:
                return home.modules[module_id]
        return None