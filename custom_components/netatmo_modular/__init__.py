"""Initialisation de l'intégration Netatmo Modular (Stable)."""
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

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup avec polling centralisé et gestion d'erreur au démarrage."""
    hass.data.setdefault(DOMAIN, {})
    
    # 1. Auth OAuth
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
    except Exception as err:
        _LOGGER.error("Erreur Auth Netatmo: %s", err)
        return False

    # 2. Définition de la logique de mise à jour unique
    async def async_update_data():
        """Fonction qui sera appelée toutes les 5 minutes."""
        try:
            await netatmo_data.async_update()
            return netatmo_data.homes_data
        except Exception as err:
            raise UpdateFailed(f"Erreur de mise à jour API: {err}")

    # 3. Création du Coordinateur
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"netatmo_central_{entry.entry_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=5),
    )

    # 4. PREMIER CHARGEMENT CRITIQUE
    # C'est ici qu'on évite l'erreur "raise ConfigEntryNotReady in forwarded platform"
    # On charge les données AVANT de lancer climate.py
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise # On laisse HA gérer le retry
    except Exception as ex:
        raise ConfigEntryNotReady(f"Echec premier chargement: {ex}") from ex

    # 5. Stockage Global
    hass.data[DOMAIN][entry.entry_id] = {
        "api": netatmo_data,
        "coordinator": coordinator
    }

    # 6. Lancement des plateformes (Climate)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)