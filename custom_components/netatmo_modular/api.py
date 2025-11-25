"""Netatmo API client."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_HOMES_DATA,
    API_HOME_STATUS,
    API_SET_ROOM_THERMPOINT,
    API_SET_THERM_MODE,
    API_SET_STATE,
    OAUTH2_TOKEN,
)

_LOGGER = logging.getLogger(__name__)


class NetatmoApiError(Exception):
    """Base exception for Netatmo API errors."""


class NetatmoAuthError(NetatmoApiError):
    """Authentication error."""


class NetatmoApiClient:
    """Netatmo API client."""

    def __init__(
        self,
        hass: HomeAssistant,
        client_id: str,
        client_secret: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        """Initialize the API client."""
        self.hass = hass
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get aiohttp session."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)
        return self._session

    def is_token_valid(self) -> bool:
        """Check if the current token is valid."""
        if not self.access_token or not self.token_expires_at:
            return False
        return datetime.now() < (self.token_expires_at - timedelta(minutes=10))

    async def async_refresh_token(self) -> dict[str, Any]:
        """Refresh the access token."""
        if not self.refresh_token:
            raise NetatmoAuthError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with self.session.post(OAUTH2_TOKEN, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise NetatmoAuthError(f"Token refresh failed: {error_text}")

            result = await response.json()
            self.access_token = result["access_token"]
            self.refresh_token = result["refresh_token"]
            self.token_expires_at = datetime.now() + timedelta(seconds=result.get("expires_in", 10800))
            return {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.token_expires_at.isoformat(),
            }

    async def _async_request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated API request."""
        if not self.is_token_valid():
            await self.async_refresh_token()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        async with self.session.request(method, url, headers=headers, **kwargs) as response:
            if response.status == 403:
                await self.async_refresh_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                async with self.session.request(method, url, headers=headers, **kwargs) as retry_resp:
                    if retry_resp.status != 200:
                        error_text = await retry_resp.text()
                        raise NetatmoApiError(f"API request failed: {retry_resp.status} - {error_text}")
                    return await retry_resp.json()

            if response.status != 200:
                error_text = await response.text()
                raise NetatmoApiError(f"API request failed: {response.status} - {error_text}")

            return await response.json()

    async def async_get_full_data(self) -> dict[str, Any]:
        """Get complete data: homes + status for each home."""
        # 1. Get Homes Data (Structure)
        result = await self._async_request("GET", API_HOMES_DATA)
        homes_data = result.get("body", {})
        homes = homes_data.get("homes", [])

        result = {
            "homes": [],
            "user": homes_data.get("user", {}),
        }

        # 2. Get Home Status (States) for each home
        for home in homes:
            home_id = home.get("id")
            if not home_id:
                continue
            try:
                status_resp = await self._async_request("GET", API_HOME_STATUS, params={"home_id": home_id})
                status = status_resp.get("body", {}).get("home", {})
                if not status:
                    _LOGGER.warning("Empty status for home %s", home_id)
                
                home_with_status = {**home, "status": status}
                result["homes"].append(home_with_status)
            except NetatmoApiError as err:
                _LOGGER.warning("Failed to get status for home %s: %s", home_id, err)
                result["homes"].append(home)

        return result

    async def async_set_state(
        self,
        home_id: str,
        room_id: str,
        mode: str,
        temp: float | None = None,
        fp: str | None = None,
    ) -> bool:
        """Set room thermostat state."""
        room_data = {"id": room_id, "therm_setpoint_mode": mode}
        if temp is not None:
            room_data["therm_setpoint_temperature"] = temp
        if fp is not None:
            room_data["therm_setpoint_fp"] = fp

        data = {"home": {"id": home_id, "rooms": [room_data]}}
        result = await self._async_request("POST", API_SET_STATE, json=data)
        return result.get("status") == "ok" or result.get("time_server") is not None

    async def async_set_module_state(
        self,
        home_id: str,
        module_id: str,
        on: bool | None = None,
        brightness: int | None = None,
    ) -> bool:
        """Set module state (Light/Plug)."""
        module_data = {"id": module_id}
        
        # Pour les modules, il faut souvent utiliser le bridge (pont) si c'est du Zigbee,
        # mais l'API setstate standard accepte directement l'ID du module dans 'modules'.
        
        if on is not None:
            module_data["on"] = on
        if brightness is not None:
            module_data["brightness"] = brightness

        data = {"home": {"id": home_id, "modules": [module_data]}}
        
        _LOGGER.debug("Setting module state: %s", data)
        result = await self._async_request("POST", API_SET_STATE, json=data)
        return result.get("status") == "ok" or result.get("time_server") is not None

    async def async_set_therm_mode(self, home_id: str, mode: str) -> bool:
        """Set home thermostat mode."""
        data = {"home_id": home_id, "mode": mode}
        result = await self._async_request("POST", API_SET_THERM_MODE, data=data)
        return result.get("status") == "ok"