"""Initialisation de l'intégration Netatmo Modular (Polling Centralisé)."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import api
from .const import DOMAIN, PLATFORMS, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Mise en place de l'entrée config avec Coordinateur Central."""
    hass.data.setdefault(DOMAIN, {})
    
    # 1. Setup OAuth
    client_id = entry.data.get(CONF_CLIENT_ID)
    client_secret = entry.data.get(CONF_CLIENT_SECRET)

    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass, DOMAIN, client_id, client_secret, OAUTH2_AUTHORIZE, OAUTH2_TOKEN
        ),
    )

    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
        netatmo_data = api.NetatmoDataHandler(hass, session)
        # On ne fait plus l'update manuel ici, le coordinateur s'en chargera
    except Exception as err:
        _LOGGER.error("Erreur connexion Netatmo: %s", err)
        return False

    # 2. Création du Coordinateur Central (Polling unique)
    async def async_update_data():
        """Fonction unique de mise à jour pour toute l'intégration."""
        await netatmo_data.async_update()
        return netatmo_data.homes_data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"netatmo_central_{entry.entry_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=5), # 5 minutes pour tout le monde
    )

    # Premier chargement immédiat
    await coordinator.async_config_entry_first_refresh()

    # 3. Stockage Global : API + Coordinateur
    hass.data[DOMAIN][entry.entry_id] = {
        "api": netatmo_data,
        "coordinator": coordinator
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Déchargement."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)