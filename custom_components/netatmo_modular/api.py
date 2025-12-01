"""API Handler pour pyatmo (Version Blindée)."""
import logging
from typing import Any

import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

_LOGGER = logging.getLogger(__name__)

class AsyncConfigEntryAuth(pyatmo.auth.AbstractAsyncAuth):
    """Adaptateur d'authentification robuste entre pyatmo et Home Assistant."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session):
        """Initialisation avec la session OAuth2 de HA."""
        self._session = session

    async def async_get_access_token(self) -> str:
        """Retourne un token valide."""
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    async def async_post_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Redirige les requêtes POST vers HA avec nettoyage agressif des arguments."""
        
        # Gestion de l'URL absolue
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        
        # On récupère les arguments potentiels
        # Note: pyatmo peut les passer via des arguments nommés ou via kwargs
        params = kwargs.get("params")
        json_payload = kwargs.get("json")
        data = kwargs.get("data")

        # --- LOGIQUE DE SAUVETAGE ---
        # Le but : S'assurer que le gros dictionnaire 'home' finit TOUJOURS dans 'json'
        # et JAMAIS dans 'params'.
        
        # 1. Vérification dans 'params'
        if params and isinstance(params, dict):
            # Cas A: params={'json': {'home': ...}} (Vu dans tes logs précédents)
            if "json" in params and isinstance(params["json"], dict):
                _LOGGER.debug("FIX API: Extraction de params['json'] vers le body JSON")
                json_payload = params["json"]
                params = None # On vide params

            # Cas B: params={'home': ...} (Vu dans ta dernière erreur)
            elif "home" in params:
                _LOGGER.debug("FIX API: Déplacement de params['home'] vers le body JSON")
                json_payload = params
                params = None

            # Cas C: params={'rooms': ...} (Autre format possible)
            elif "rooms" in params:
                _LOGGER.debug("FIX API: Déplacement de params['rooms'] vers le body JSON")
                json_payload = params
                params = None

        # 2. Vérification dans 'data' (au cas où)
        if data and isinstance(data, dict) and ( "home" in data or "rooms" in data ):
             if json_payload is None:
                 json_payload = data
                 data = None

        # Mise à jour des kwargs pour l'appel final
        if params is not None:
            kwargs["params"] = params
        else:
            kwargs.pop("params", None) # On retire la clé si elle est vide/None

        if json_payload is not None:
            kwargs["json"] = json_payload
        
        if data is not None:
            kwargs["data"] = data
        else:
            kwargs.pop("data", None)

        # Log final pour vérification
        # _LOGGER.debug("POST SAFE %s | json=%s | params=%s", url, json_payload, params)

        return await self._session.async_request("POST", url, **kwargs)

    async def async_get_api_request(
        self, endpoint: str, params: dict = None, **kwargs: Any
    ) -> Any:
        """Redirige les requêtes GET."""
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        return await self._session.async_request("GET", url, params=params, **kwargs)


class NetatmoDataHandler:
    """Gère les appels pyatmo pour tout le compte."""

    def __init__(self, hass: HomeAssistant, session: config_entry_oauth2_flow.OAuth2Session):
        self.hass = hass
        self.session = session
        self.auth = AsyncConfigEntryAuth(session)
        self.account = pyatmo.AsyncAccount(self.auth)
        self.homes_data = {}

    async def async_update(self):
        """Rafraîchir les données."""
        try:
            await self.account.async_update_topology()
            self.homes_data = self.account.homes
        except Exception as err:
            _LOGGER.error("Erreur update Netatmo: %s", err)
            raise err