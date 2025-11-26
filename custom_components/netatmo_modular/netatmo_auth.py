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
        
        self.websession = session
        # CORRECTIF : On s'assure qu'il n'y a pas de slash à la fin pour éviter les doublons
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
        try:
            token = await self.async_get_access_token()
        except Exception as err:
            logging.getLogger(__name__).error("Erreur lors de la récupération du token: %s", err)
            raise

        headers = {"Authorization": f"Bearer {token}"}
        
        # --- CORRECTIF URL ---
        # Si l'URL n'est pas complète (pas http...)
        if not url.startswith("http"):
            # Si l'URL relative ne commence pas par un slash, on l'ajoute
            if not url.startswith("/"):
                url = f"/{url}"
            # On concatène proprement
            url = f"{self.base_url}{url}"

        async with self._session.request(
            method, url, headers=headers, json=data, params=params
        ) as resp:
            resp.raise_for_status()
            return await resp.read()