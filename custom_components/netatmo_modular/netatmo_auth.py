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
        # pyatmo gère la logique, ici on passe juste la requête
        headers = {"Authorization": f"Bearer {await self.async_get_access_token()}"}
        async with self._session.request(
            method, url, headers=headers, json=data, params=params
        ) as resp:
            return await resp.read()