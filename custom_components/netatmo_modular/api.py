"""API Handler pour pyatmo (Version Stable - Topologie Force)."""
import logging
from typing import Any

import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

_LOGGER = logging.getLogger(__name__)

class AsyncConfigEntryAuth(pyatmo.auth.AbstractAsyncAuth):
    """Adaptateur d'authentification."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session):
        self._session = session

    async def async_get_access_token(self) -> str:
        """Retourne un token valide."""
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    async def async_post_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Envoi POST avec correction automatique des arguments."""
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        
        # Correction identique à précédemment pour le setstate
        params = kwargs.get("params")
        data = kwargs.get("data")
        json_payload = kwargs.get("json")

        if params and isinstance(params, dict):
            if "rooms" in params or "home" in params or "json" in params:
                if "json" in params:
                    json_payload = params["json"]
                else:
                    json_payload = params
                kwargs["params"] = None

        if data and isinstance(data, dict):
             if "rooms" in data or "home" in data:
                 json_payload = data
                 kwargs["data"] = None

        if json_payload:
            kwargs["json"] = json_payload

        return await self._session.async_request("POST", url, **kwargs)

    async def async_get_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Envoi GET standard."""
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        return await self._session.async_request("GET", url, **kwargs)


class NetatmoDataHandler:
    """Gestionnaire de données."""

    def __init__(self, hass: HomeAssistant, session: config_entry_oauth2_flow.OAuth2Session):
        self.hass = hass
        self.session = session
        self.auth = AsyncConfigEntryAuth(session)
        self.account = pyatmo.AsyncAccount(self.auth)
        self.homes_data = {}

    async def async_update(self):
        """Mise à jour des données."""
        try:
            # CORRECTION : On force update_topology à chaque fois.
            # update_status est trop fragile pour certains appareils Legrand/Fil Pilote.
            # Avec un intervalle de 5min, c'est parfaitement safe pour les quotas.
            await self.account.async_update_topology()
            
            self.homes_data = self.account.homes
            
        except Exception as err:
            _LOGGER.error("Erreur update Netatmo: %s", err)
            raise err