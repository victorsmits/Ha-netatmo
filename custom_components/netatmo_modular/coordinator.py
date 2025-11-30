from __future__ import annotations

from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyatmo import AsyncAccount
from .const import DOMAIN, UPDATE_INTERVAL

class NetatmoDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, account: AsyncAccount) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=UPDATE_INTERVAL))
        self.config_entry = config_entry
        self.account = account
        self.homes = {}

    async def _async_update_data(self) -> dict:
        try:
            await self.account.async_update_topology()
            if self.account.homes:
                for home_id in self.account.homes:
                    try:
                        await self.account.async_update_status(home_id)
                    except Exception as err:
                        if "No device found" not in str(err):
                            raise err
            self.homes = self.account.homes
            return self.homes
        except Exception as err:
            raise UpdateFailed(f"Netatmo sync error: {err}") from err

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

import logging
_LOGGER = logging.getLogger(__name__)