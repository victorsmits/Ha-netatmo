"""Netatmo Modular integration for Home Assistant."""
from __future__ import annotations

import logging
import json
import pyatmo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components import webhook
from homeassistant.helpers import device_registry as dr

from .api import NetatmoApiClient, NetatmoAuth
from .config_flow import NetatmoOAuth2Implementation
from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN, CONF_EXTERNAL_URL
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.LIGHT]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Netatmo Modular."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Auth Implementation
    implementation = config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    
    # 2. Session OAuth pour HA
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    
    # 3. Auth Wrapper pour Pyatmo
    auth_wrapper = NetatmoAuth(async_get_clientsession(hass), session)
    
    # 4. Compte Pyatmo
    try:
        account = pyatmo.AsyncAccount(auth_wrapper)
    except Exception as err:
        _LOGGER.error("Failed to init pyatmo: %s", err)
        return False

    # 5. Client & Coordinator
    api_client = NetatmoApiClient(hass, account)
    coordinator = NetatmoDataUpdateCoordinator(hass, entry, api_client)
    
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 6. Enregistrement des Devices (Homes)
    device_registry = dr.async_get(hass)
    for home in coordinator.homes.values():
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, home.entity_id)},
            manufacturer="Netatmo",
            name=home.name,
            model="Home",
            configuration_url="https://home.netatmo.com",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 7. Webhook
    webhook_id = entry.entry_id
    webhook.async_register(
        hass, DOMAIN, "Netatmo Modular", webhook_id, handle_webhook
    )
    
    external_url = entry.data.get(CONF_EXTERNAL_URL, "").rstrip("/")
    if external_url:
        webhook_url = f"{external_url}/api/webhook/{webhook_id}"
        await api_client.async_register_webhook(webhook_url)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload."""
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.api.async_drop_webhook()

    webhook.async_unregister(hass, entry.entry_id)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def handle_webhook(hass: HomeAssistant, webhook_id: str, request) -> None:
    """Handle webhook."""
    try:
        text_data = await request.text()
        _LOGGER.debug("WEBHOOK: %s", text_data)
        data = json.loads(text_data)
    except Exception:
        return

    if DOMAIN in hass.data and webhook_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][webhook_id]
        await coordinator.async_handle_webhook(data)