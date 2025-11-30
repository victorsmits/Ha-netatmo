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
            # 1. Structure (Topology)
            await self.account.async_update_topology()
            
            # 2. Statuts (Températures, etc.)
            # On boucle sur chaque maison pour mettre à jour son statut individuellement
            if self.account.homes:
                for home_id in self.account.homes:
                    try:
                        await self.account.async_update_status(home_id)
                    except Exception as err:
                        _LOGGER.warning(
                            "Erreur maj statut maison %s: %s", home_id, err
                        )
            
            self.homes = self.account.homes
            return self.homes
            
        except Exception as err:
            raise UpdateFailed(f"Erreur globale Netatmo: {err}") from err

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