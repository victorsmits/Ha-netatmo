from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, device_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pyatmo import AsyncAccount
from .netatmo_auth import HAModularAuth
from .const import DOMAIN, CONF_CLIENT_ID, CONF_CLIENT_SECRET, OAUTH2_AUTHORIZE, OAUTH2_TOKEN
from .coordinator import NetatmoDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.LIGHT]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    implementation = config_entry_oauth2_flow.LocalOAuth2Implementation(
        hass, DOMAIN, entry.data[CONF_CLIENT_ID], entry.data[CONF_CLIENT_SECRET],
        OAUTH2_AUTHORIZE, OAUTH2_TOKEN
    )
    config_entry_oauth2_flow.async_register_implementation(hass, DOMAIN, implementation)

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    auth = HAModularAuth(session, async_get_clientsession(hass))
    account = AsyncAccount(auth)

    coordinator = NetatmoDataUpdateCoordinator(hass, entry, account)
    await coordinator.async_config_entry_first_refresh()

    dr = device_registry.async_get(hass)
    for home in coordinator.homes.values():
        dr.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, home.entity_id)},
            name=home.name,
            manufacturer="Netatmo",
            model="Home",
            configuration_url="https://my.netatmo.com"
        )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "account": account,
        "auth": auth
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok