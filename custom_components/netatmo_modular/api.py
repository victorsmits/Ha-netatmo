"""API Handler pour pyatmo."""
import logging
from typing import Any

import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

class AsyncConfigEntryAuth(pyatmo.auth.AbstractAsyncAuth):
    """Adaptateur d'authentification entre pyatmo et Home Assistant."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session):
        """Initialisation avec la session OAuth2 de HA."""
        self._session = session

    async def async_get_access_token(self) -> str:
        """Retourne un token valide."""
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    async def async_post_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Redirige les requêtes POST de pyatmo vers la session HA."""
        # pyatmo s'attend à une réponse aiohttp brute
        return await self._session.async_request("POST", endpoint, **kwargs)

    async def async_get_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Redirige les requêtes GET de pyatmo vers la session HA."""
        return await self._session.async_request("GET", endpoint, **kwargs)


class NetatmoDataHandler:
    """Gère les appels pyatmo pour tout le compte."""

    def __init__(self, hass: HomeAssistant, session: config_entry_oauth2_flow.OAuth2Session):
        self.hass = hass
        # On utilise notre adaptateur au lieu de la session brute
        self.auth = AsyncConfigEntryAuth(session)
        self.account = pyatmo.AsyncAccount(self.auth)
        self.homes_data = {}

    async def async_update(self):
        """Rafraîchir les données de toutes les maisons."""
        try:
            # update_topology met à jour la structure ET les états
            await self.account.async_update_topology()
            self.homes_data = self.account.homes
        except Exception as err:
            _LOGGER.error("Erreur update Netatmo: %s", err)
            raise err