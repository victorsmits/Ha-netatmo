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
        # Add 10 minute buffer
        return datetime.now() < (self.token_expires_at - timedelta(minutes=10))

    async def async_refresh_token(self) -> dict[str, Any]:
        """Refresh the access token."""
        if not self.refresh_token:
            raise NetatmoAuthError("No refresh token available")

        _LOGGER.debug("Refreshing Netatmo access token")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with self.session.post(OAUTH2_TOKEN, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Token refresh failed: %s - %s", response.status, error_text)
                raise NetatmoAuthError(f"Token refresh failed: {error_text}")

            result = await response.json()

            self.access_token = result["access_token"]
            self.refresh_token = result["refresh_token"]
            self.token_expires_at = datetime.now() + timedelta(
                seconds=result.get("expires_in", 10800)
            )

            _LOGGER.debug("Token refreshed successfully, expires at %s", self.token_expires_at)

            return {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.token_expires_at.isoformat(),
            }

    async def _async_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an authenticated API request."""
        # Refresh token if needed
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
                # Token might be invalid, try to refresh
                _LOGGER.warning("Got 403, attempting token refresh")
                await self.async_refresh_token()
                # Retry the request
                headers["Authorization"] = f"Bearer {self.access_token}"
                async with self.session.request(method, url, headers=headers, **kwargs) as retry_response:
                    if retry_response.status != 200:
                        error_text = await retry_response.text()
                        raise NetatmoApiError(f"API request failed: {retry_response.status} - {error_text}")
                    return await retry_response.json()

            if response.status != 200:
                error_text = await response.text()
                raise NetatmoApiError(f"API request failed: {response.status} - {error_text}")

            return await response.json()

    async def async_get_homes_data(self) -> dict[str, Any]:
        """Get all homes data including rooms and modules."""
        _LOGGER.debug("Fetching homes data")
        result = await self._async_request("GET", API_HOMES_DATA)
        return result.get("body", {})

    async def async_get_home_status(self, home_id: str) -> dict[str, Any]:
        """Get current status of a home."""
        _LOGGER.debug("Fetching home status for %s", home_id)
        result = await self._async_request(
            "GET",
            API_HOME_STATUS,
            params={"home_id": home_id},
        )
        return result.get("body", {}).get("home", {})

    async def async_set_room_thermpoint(
        self,
        home_id: str,
        room_id: str,
        mode: str,
        temp: float | None = None,
        end_time: int | None = None,
    ) -> bool:
        """Set room thermostat point."""
        _LOGGER.debug(
            "Setting room thermpoint: home=%s, room=%s, mode=%s, temp=%s",
            home_id,
            room_id,
            mode,
            temp,
        )

        data: dict[str, Any] = {
            "home_id": home_id,
            "room_id": room_id,
            "mode": mode,
        }

        if temp is not None:
            data["temp"] = temp

        if end_time is not None:
            data["endtime"] = end_time

        result = await self._async_request(
            "POST",
            API_SET_ROOM_THERMPOINT,
            data=data,
        )

        return result.get("status") == "ok"

    async def async_set_therm_mode(
        self,
        home_id: str,
        mode: str,
        end_time: int | None = None,
    ) -> bool:
        """Set home thermostat mode."""
        _LOGGER.debug("Setting therm mode: home=%s, mode=%s", home_id, mode)

        data: dict[str, Any] = {
            "home_id": home_id,
            "mode": mode,
        }

        if end_time is not None:
            data["endtime"] = end_time

        result = await self._async_request(
            "POST",
            API_SET_THERM_MODE,
            data=data,
        )

        return result.get("status") == "ok"

    async def async_get_full_data(self) -> dict[str, Any]:
        """Get complete data: homes + status for each home."""
        homes_data = await self.async_get_homes_data()
        homes = homes_data.get("homes", [])

        result = {
            "homes": [],
            "user": homes_data.get("user", {}),
        }

        for home in homes:
            home_id = home.get("id")
            if not home_id:
                continue

            try:
                status = await self.async_get_home_status(home_id)
                home_with_status = {
                    **home,
                    "status": status,
                }
                result["homes"].append(home_with_status)
            except NetatmoApiError as err:
                _LOGGER.warning("Failed to get status for home %s: %s", home_id, err)
                result["homes"].append(home)

        return result
