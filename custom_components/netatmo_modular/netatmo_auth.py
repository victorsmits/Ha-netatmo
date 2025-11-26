import logging
from typing import Any
from aiohttp import ClientSession
from pyatmo.auth import AbstractAsyncAuth
from homeassistant.helpers import config_entry_oauth2_flow

class HAModularAuth(AbstractAsyncAuth):
    """Liaison entre l'OAuth de HA et Pyatmo."""

    def __init__(
        self, 
        oauth_session: config_entry_oauth2_flow.OAuth2Session, 
        session: ClientSession
    ) -> None:
        """Initialisation."""
        self._oauth_session = oauth_session
        self._session = session
        
        # --- CORRECTIFS PYATMO ---
        # 1. Pyatmo cherche obligatoirement un attribut 'websession'
        self.websession = session
        # 2. Pyatmo a besoin de connaître l'URL de base pour construire les requêtes
        self.base_url = "https://api.netatmo.com"

    async def async_get_access_token(self) -> str:
        """Retourne un token valide."""
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]

    async def async_make_api_request(
        self, 
        method: str, 
        url: str, 
        data: dict[str, Any] | None = None, 
        params: dict[str, Any] | None = None
    ) -> bytes:
        """Exécute une requête via la session HA."""
        # Obtention du token
        try:
            token = await self.async_get_access_token()
        except Exception as err:
            logging.getLogger(__name__).error("Erreur lors de la récupération du token: %s", err)
            raise

        headers = {"Authorization": f"Bearer {token}"}
        
        # Si Pyatmo envoie une URL relative (ex: /api/homestatus), on la complète
        if not url.startswith("http"):
            url = f"{self.base_url}{url}"

        async with self._session.request(
            method, url, headers=headers, json=data, params=params
        ) as resp:
            # On lève une exception si le statut HTTP n'est pas bon (4xx, 5xx)
            resp.raise_for_status()
            return await resp.read()