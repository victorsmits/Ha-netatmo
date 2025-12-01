"""API Handler propre utilisant pyatmo."""
import logging
from typing import Any

import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

_LOGGER = logging.getLogger(__name__)

class AsyncConfigEntryAuth(pyatmo.auth.AbstractAsyncAuth):
    """Adaptateur d'authentification standard HA -> Pyatmo."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session):
        self._session = session

    async def async_get_access_token(self) -> str:
        """Retourne un token valide (refresh auto géré par HA)."""
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    async def async_post_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Passe la main à la session HA pour le POST."""
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        return await self._session.async_request("POST", url, **kwargs)

    async def async_get_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Passe la main à la session HA pour le GET."""
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        return await self._session.async_request("GET", url, **kwargs)


class NetatmoDataHandler:
    """Gestionnaire de données haut niveau."""

    def __init__(self, hass: HomeAssistant, session: config_entry_oauth2_flow.OAuth2Session):
        self.hass = hass
        self.session = session
        self.auth = AsyncConfigEntryAuth(session)
        # On instancie pyatmo proprement
        self.account = pyatmo.AsyncAccount(self.auth)
        self.homes_data = {}

    async def async_update(self):
        """Met à jour la topologie et les états."""
        try:
            await self.account.async_update_topology()
            self.homes_data = self.account.homes
        except Exception as err:
            _LOGGER.error("Erreur update Netatmo: %s", err)
            raise err