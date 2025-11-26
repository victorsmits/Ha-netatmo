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
    """Set up Netatmo Modular from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Enregistrement de l'implémentation OAuth2
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

    # --- MIGRATIONS ---
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
    
    # 3. Récupération de l'implémentation
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    
    # 4. Création de la session
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    
    # 5. Initialisation Pyatmo
    auth = HAModularAuth(session, async_get_clientsession(hass))
    account = AsyncAccount(auth)

    # 6. Gestion du Webhook ID
    if CONF_WEBHOOK_ID not in entry.data:
        new_data = entry.data.copy()
        new_data[CONF_WEBHOOK_ID] = webhook.async_generate_id()
        hass.config_entries.async_update_entry(entry, data=new_data)
    
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # 7. Initialiser le Coordinator
    coordinator = NetatmoDataUpdateCoordinator(hass, entry, account)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "account": account,
        "auth": auth
    }

    # 8. Enregistrement du Webhook dans HA
    webhook.async_register(
        hass, DOMAIN, "Netatmo Modular", webhook_id, get_webhook_handler(coordinator)
    )

    # 9. Enregistrement du Webhook chez Netatmo (Cloud)
    external_url = entry.data.get(CONF_EXTERNAL_URL) 
    if not external_url:
         try:
            external_url = hass.components.cloud.async_remote_ui_url()
         except AttributeError:
            external_url = hass.config.external_url

    if external_url:
        webhook_url = f"{external_url}{webhook.async_generate_path(webhook_id)}"
        _LOGGER.info("Configuration du webhook Netatmo sur: %s", webhook_url)
        
        try:
            # CORRECTIF : On supprime d'abord l'ancien webhook pour nettoyer
            await auth.async_make_api_request("POST", "api/dropwebhook", data={"app_types": "app_thermostat"})
            
            # On enregistre le nouveau
            await auth.async_make_api_request("POST", "api/addwebhook", data={"url": webhook_url})
            _LOGGER.info("Webhook Netatmo enregistré avec succès !")
        except Exception as e:
            _LOGGER.warning("Erreur lors de l'enregistrement du webhook (vérifiez votre URL externe) : %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

def get_webhook_handler(coordinator: NetatmoDataUpdateCoordinator):
    """Crée le handler pour traiter les événements entrants."""
    async def async_handle_webhook(hass, webhook_id, request):
        try:
            # On lit le message mais on ne l'affiche qu'en debug
            # Cela évite de spammer les logs
            message = await request.json()
            _LOGGER.debug("Webhook Netatmo reçu : %s", message)
            
            # On rafraichit les données immédiatement
            await coordinator.async_request_refresh()
            
        except Exception as ex:
            _LOGGER.error("Erreur traitement webhook : %s", ex)
        
        return None

    return async_handle_webhook

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok