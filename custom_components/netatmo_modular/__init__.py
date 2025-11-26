"""Netatmo Modular integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.components import webhook
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pyatmo import AsyncAccount
from .netatmo_auth import HAModularAuth
from .const import DOMAIN, CONF_EXTERNAL_URL, CONF_CLIENT_ID, CONF_CLIENT_SECRET
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.LIGHT]

OAUTH2_AUTHORIZE = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN = "https://api.netatmo.com/oauth2/token"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Netatmo Modular from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Enregistrement de l'implémentation OAuth2
    # C'est nécessaire car vous utilisez des credentials personnalisés stockés dans la config
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

    # 2. MIGRATION : Correction du KeyError 'auth_implementation'
    # Si l'entrée vient de l'ancienne version, cette clé manque. On l'ajoute.
    if "auth_implementation" not in entry.data:
        _LOGGER.info("Migration de la configuration : ajout de auth_implementation")
        hass.config_entries.async_update_entry(
            entry, 
            data={**entry.data, "auth_implementation": DOMAIN}
        )

    # 3. Récupération de l'implémentation (maintenant ça ne plantera plus)
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    
    # 4. Création de la session
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    
    # 5. Initialisation Pyatmo
    auth = HAModularAuth(session, async_get_clientsession(hass))
    account = AsyncAccount(auth)

    # 6. Gestion du Webhook ID (création si inexistant)
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
        "account": account
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
        _LOGGER.info("Enregistrement du webhook Netatmo sur: %s", webhook_url)
        try:
            # Note: pyatmo v8 gère async_set_webhook via l'account ou l'auth selon les versions
            # Vérifiez si votre version de pyatmo utilise bien cette méthode sur account
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
            
            # Filtrage basique pour éviter de refresh sur des pings inutiles
            # Netatmo envoie souvent "user_id" ou des push events
            await coordinator.async_request_refresh()
                
        except Exception as ex:
            _LOGGER.error("Erreur traitement webhook: %s", ex)
        
        return None

    return async_handle_webhook

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    
    # Optionnel: supprimer le webhook coté Netatmo
    # account = hass.data[DOMAIN][entry.entry_id]["account"]
    # await account.async_drop_webhook()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok