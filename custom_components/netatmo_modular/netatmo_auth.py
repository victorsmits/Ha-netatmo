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
        # CORRECTIF CRITIQUE : Le slash à la fin est OBLIGATOIRE car Pyatmo fait une concaténation simple
        self.base_url = "https://api.netatmo.com/"

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
            logging.getLogger(__name__).error("Erreur token: %s", err)
            raise

        headers = {"Authorization": f"Bearer {token}"}
        
        # Sécurité : Si l'URL n'est pas complète, on la reconstruit proprement
        if not url.startswith("http"):
            # On retire le slash initial s'il y en a un pour éviter le double slash
            # car self.base_url en a déjà un maintenant.
            clean_path = url.lstrip("/")
            url = f"{self.base_url}{clean_path}"

        async with self._session.request(
            method, url, headers=headers, json=data, params=params
        ) as resp:
            resp.raise_for_status()
            return await resp.read()