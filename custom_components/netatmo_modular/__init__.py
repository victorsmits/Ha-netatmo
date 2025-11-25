"""Netatmo Modular integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_entry_oauth2_flow

from .api import NetatmoApiClient, NetatmoAuthError
from .config_flow import NetatmoOAuth2Implementation
from .const import DOMAIN
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Netatmo Modular from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get credentials from config entry
    client_id = entry.data.get("client_id")
    client_secret = entry.data.get("client_secret")
    token_data = entry.data.get("token", {})

    if not client_id or not client_secret:
        raise ConfigEntryAuthFailed("Missing client credentials")

    # Register OAuth2 implementation for potential reauth
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        NetatmoOAuth2Implementation(
            hass,
            DOMAIN,
            client_id,
            client_secret,
        ),
    )

    # Parse token data
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_at_str = token_data.get("expires_at")

    if not access_token or not refresh_token:
        raise ConfigEntryAuthFailed("Missing tokens, please reconfigure")

    # Parse expires_at
    token_expires_at = None
    if expires_at_str:
        try:
            if isinstance(expires_at_str, (int, float)):
                token_expires_at = datetime.fromtimestamp(expires_at_str)
            else:
                token_expires_at = datetime.fromisoformat(expires_at_str)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse token expiry: %s", expires_at_str)

    # Create API client
    api_client = NetatmoApiClient(
        hass=hass,
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
    )

    # Test the connection and refresh token if needed
    try:
        if not api_client.is_token_valid():
            _LOGGER.info("Token expired or expiring soon, refreshing...")
            await api_client.async_refresh_token()
    except NetatmoAuthError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect to Netatmo: {err}") from err

    # Create coordinator
    coordinator = NetatmoDataUpdateCoordinator(
        hass=hass,
        config_entry=entry,
        api_client=api_client,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
