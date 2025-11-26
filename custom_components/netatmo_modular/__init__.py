"""Netatmo Modular integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, device_registry as dr
from homeassistant.components import webhook
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pyatmo import AsyncAccount
from .netatmo_auth import HAModularAuth
from .const import DOMAIN, CONF_EXTERNAL_URL
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.LIGHT]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Netatmo Modular from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Configuration OAuth
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    
    # 2. Initialisation Pyatmo
    auth = HAModularAuth(session, async_get_clientsession(hass))
    account = AsyncAccount(auth)

    # 3. Gestion du Webhook ID (création si inexistant)
    if CONF_WEBHOOK_ID not in entry.data:
        new_data = entry.data.copy()
        new_data[CONF_WEBHOOK_ID] = webhook.async_generate_id()
        hass.config_entries.async_update_entry(entry, data=new_data)
    
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # 4. Initialiser le Coordinator (modifié pour pyatmo)
    coordinator = NetatmoDataUpdateCoordinator(hass, entry, account)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "account": account
    }

    # 5. Enregistrement du Webhook dans HA
    webhook.async_register(
        hass, DOMAIN, "Netatmo Modular", webhook_id, get_webhook_handler(coordinator)
    )

    # 6. Enregistrement du Webhook chez Netatmo (Cloud)
    # On récupère l'URL externe configurée
    external_url = entry.data.get(CONF_EXTERNAL_URL) 
    # Ou l'URL interne HA si non définie (mais Netatmo exige du HTTPS valide externe)
    if not external_url:
         try:
            external_url = hass.components.cloud.async_remote_ui_url()
         except AttributeError:
            external_url = hass.config.external_url

    if external_url:
        webhook_url = f"{external_url}{webhook.async_generate_path(webhook_id)}"
        _LOGGER.info("Enregistrement du webhook Netatmo sur: %s", webhook_url)
        try:
            await account.async_set_webhook(webhook_url)
        except Exception as e:
            _LOGGER.warning("Impossible d'enregistrer le webhook chez Netatmo: %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

def get_webhook_handler(coordinator: NetatmoDataUpdateCoordinator):
    """Crée le handler pour traiter les événements entrants."""
    async def async_handle_webhook(hass, webhook_id, request):
        try:
            message = await request.json()
            _LOGGER.debug("Webhook reçu: %s", message)
            
            # Gestion basique : on force un refresh des données
            # Idéalement, on trie par type d'événement (therm_setpoint, connection, etc.)
            event_type = message.get("event_type")
            
            # Exemples d'événements intéressants
            triggers = ["set_point", "therm_mode", "cancel_set_point"]
            
            if any(t in str(message) for t in triggers):
                _LOGGER.info("Mise à jour déclenchée par webhook (%s)", event_type)
                await coordinator.async_request_refresh()
                
        except Exception as ex:
            _LOGGER.error("Erreur traitement webhook: %s", ex)
        
        return None

    return async_handle_webhook

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Désenregistrer le webhook chez Netatmo (optionnel mais propre)
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    
    # Drop webhook chez Netatmo via pyatmo si nécessaire
    # account = hass.data[DOMAIN][entry.entry_id]["account"]
    # await account.async_drop_webhook()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok