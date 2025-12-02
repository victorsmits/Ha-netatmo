"""API Handler pour pyatmo (Version Robuste & Blindée)."""
import logging
from typing import Any

import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

_LOGGER = logging.getLogger(__name__)

class AsyncConfigEntryAuth(pyatmo.auth.AbstractAsyncAuth):
    """Adaptateur d'authentification intelligent."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session):
        self._session = session

    async def async_get_access_token(self) -> str:
        """Retourne un token valide."""
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    async def async_post_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Envoi POST avec correction automatique des arguments."""
        
        # 1. URL Absolue
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        
        # 2. CORRECTION CRITIQUE : Pyatmo vs Aiohttp
        # Pyatmo passe parfois le payload dans 'params' ou 'data'.
        # Aiohttp refuse les dictionnaires complexes dans 'params'.
        # On déplace tout ce qui ressemble à un payload JSON vers le kwarg 'json'.
        
        params = kwargs.get("params")
        data = kwargs.get("data")
        json_payload = kwargs.get("json")

        # Analyse de 'params'
        if params and isinstance(params, dict):
            # Si params contient la clé 'rooms', 'home' ou 'json', c'est le payload !
            if "rooms" in params or "home" in params:
                _LOGGER.debug("API FIX: Déplacement de params[...] vers json")
                json_payload = params
                kwargs["params"] = None # On vide params
            elif "json" in params:
                _LOGGER.debug("API FIX: Déplacement de params['json'] vers json")
                json_payload = params["json"]
                kwargs["params"] = None

        # Analyse de 'data' (au cas où)
        if data and isinstance(data, dict):
             if "rooms" in data or "home" in data:
                 json_payload = data
                 kwargs["data"] = None

        # Mise à jour finale des arguments
        if json_payload:
            kwargs["json"] = json_payload

        # _LOGGER.debug(f"POST {url} | json={kwargs.get('json')}")

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
        """Mise à jour topology."""
        try:
            await self.account.async_update_topology()
            self.homes_data = self.account.homes
        except Exception as err:
            _LOGGER.error("Erreur update Netatmo: %s", err)
            raise err