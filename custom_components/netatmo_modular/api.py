"""Netatmo API client using pyatmo."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession
from pyatmo import AbstractAsyncAuth, NetatmoError, AsyncAccount

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

_LOGGER = logging.getLogger(__name__)

class NetatmoAuth(AbstractAsyncAuth):
    """Authentication wrapper for pyatmo."""

    def __init__(
        self,
        websession: ClientSession,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize the auth."""
        self._oauth_session = oauth_session
        self._websession = websession

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]

    async def async_post_request(self, url: str, params: dict[str, Any] | None = None, data: Any = None, json: Any = None) -> Any:
        """Make a POST request."""
        await self._oauth_session.async_ensure_token_valid()
        headers = {"Authorization": f"Bearer {self._oauth_session.token['access_token']}"}
        
        # Pyatmo envoie parfois data, parfois json
        async with self._websession.post(url, headers=headers, params=params, data=data, json=json) as resp:
            resp.raise_for_status()
            return await resp.json() # Pyatmo s'attend souvent à récupérer le JSON directement ou la réponse

    async def async_get_request(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request."""
        await self._oauth_session.async_ensure_token_valid()
        headers = {"Authorization": f"Bearer {self._oauth_session.token['access_token']}"}
        async with self._websession.get(url, headers=headers, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

class NetatmoApiClient:
    """High level client."""

    def __init__(self, hass: HomeAssistant, account: AsyncAccount) -> None:
        self.hass = hass
        self.account = account

    async def async_update_data(self) -> None:
        """Fetch all data."""
        # Cette commande magique de pyatmo récupère homesdata ET homestatus
        await self.account.async_update_topology()
        await self.account.async_update_status()

    async def async_register_webhook(self, webhook_url: str) -> bool:
        """Register webhook (Force app_leg)."""
        # Pyatmo n'a pas toujours de méthode publique simple pour forcer app_leg
        # On utilise l'auth wrapper pour faire l'appel brut critique
        try:
            _LOGGER.info("Registering webhook: %s", webhook_url)
            
            # 1. Enregistrement Legrand (Prioritaire)
            await self.account.auth.async_post_request(
                "https://api.netatmo.com/api/addwebhook",
                data={"url": webhook_url, "app_type": "app_leg"}
            )
            _LOGGER.info("SUCCESS: Registered 'app_leg' webhook")
            
            # 2. Enregistrement Standard
            await self.account.auth.async_post_request(
                "https://api.netatmo.com/api/addwebhook",
                data={"url": webhook_url}
            )
            return True
        except Exception as err:
            _LOGGER.error("Webhook registration failed: %s", err)
            return False

    async def async_drop_webhook(self) -> None:
        """Drop webhooks."""
        try:
            await self.account.auth.async_post_request("https://api.netatmo.com/api/dropwebhook", data={"app_type": "app_leg"})
            await self.account.auth.async_post_request("https://api.netatmo.com/api/dropwebhook", data={})
        except Exception:
            pass