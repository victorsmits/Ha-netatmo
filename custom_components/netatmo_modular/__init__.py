"""Netatmo Modular integration."""
from __future__ import annotations

import logging
from datetime import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.components import webhook
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pyatmo import AsyncAccount
from .netatmo_auth import HAModularAuth
from .const import DOMAIN, CONF_EXTERNAL_URL, CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_WEBHOOK_ID
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.LIGHT]

OAUTH2_AUTHORIZE = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN = "https://api.netatmo.com/oauth2/token"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Netatmo Modular."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Register OAuth
    client_id = entry.data.get(CONF_CLIENT_ID)
    client_secret = entry.data.get(CONF_CLIENT_SECRET)

    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass,
            DOMAIN,
            client_id,
            client_secret,
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        ),
    )

    # 2. Migration des données (Token & Auth)
    updated_data = entry.data.copy()
    changed = False

    if "auth_implementation" not in updated_data:
        updated_data["auth_implementation"] = DOMAIN
        changed = True

    token = updated_data.get("token", {})
    if token and isinstance(token.get("expires_at"), str):
        try:
            dt = datetime.fromisoformat(token["expires_at"])
            token["expires_at"] = dt.timestamp()
            updated_data["token"] = token
            changed = True
        except Exception:
            pass

    if changed:
        hass.config_entries.async_update_entry(entry, data=updated_data)

    # 3. Setup Auth & Account
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    auth = HAModularAuth(session, async_get_clientsession(hass))
    account = AsyncAccount(auth)

    # 4. Webhook ID
    if CONF_WEBHOOK_ID not in entry.data:
        new_data = entry.data.copy()
        new_data[CONF_WEBHOOK_ID] = webhook.async_generate_id()
        hass.config_entries.async_update_entry(entry, data=new_data)
    
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # 5. Coordinator
    coordinator = NetatmoDataUpdateCoordinator(hass, entry, account)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "account": account,
        "auth": auth
    }

    # 6. Register Webhook HA
    # CORRECTIF : On essaie de désenregistrer l'ancien webhook "coincé" avant d'enregistrer le nouveau
    try:
        webhook.async_unregister(hass, webhook_id)
    except ValueError:
        pass # Il n'était pas enregistré, c'est normal

    webhook.async_register(
        hass, DOMAIN, "Netatmo Modular", webhook_id, get_webhook_handler(coordinator)
    )

    # 7. Register Webhook Cloud (Manual API call)
    external_url = entry.data.get(CONF_EXTERNAL_URL)
    if not external_url:
         try:
            external_url = hass.components.cloud.async_remote_ui_url()
         except AttributeError:
            external_url = hass.config.external_url

    if external_url:
        webhook_url = f"{external_url}{webhook.async_generate_path(webhook_id)}"
        _LOGGER.info("Enregistrement Webhook : %s", webhook_url)
        try:
            # Drop old webhook then add new one
            await auth.async_make_api_request("POST", "api/dropwebhook", data={"app_types": "app_thermostat"})
            await auth.async_make_api_request("POST", "api/addwebhook", data={"url": webhook_url})
        except Exception as e:
            _LOGGER.warning("Echec enregistrement webhook (non bloquant): %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

def get_webhook_handler(coordinator: NetatmoDataUpdateCoordinator):
    async def async_handle_webhook(hass, webhook_id, request):
        try:
            await request.json()
            await coordinator.async_request_refresh()
        except Exception:
            pass
        return None
    return async_handle_webhook

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Sécurité lors du déchargement
    try:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    except ValueError:
        pass

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok