import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady
from . import api
from .const import DOMAIN, PLATFORMS, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass, DOMAIN, entry.data[CONF_CLIENT_ID], entry.data[CONF_CLIENT_SECRET],
            OAUTH2_AUTHORIZE, OAUTH2_TOKEN
        ),
    )

    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
        netatmo_data = api.NetatmoDataHandler(hass, session)
    except Exception:
        return False

    async def async_update_data():
        try:
            await netatmo_data.async_update()
            return netatmo_data.homes_data
        except Exception as err:
            raise UpdateFailed(f"API Error: {err}")

    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name=f"netatmo_central_{entry.entry_id}",
        update_method=async_update_data, update_interval=timedelta(minutes=1),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except Exception as ex:
        raise ConfigEntryNotReady(f"Load failed: {ex}") from ex

    hass.data[DOMAIN][entry.entry_id] = {"api": netatmo_data, "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)