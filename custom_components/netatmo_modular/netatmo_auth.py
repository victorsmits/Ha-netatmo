from typing import Any
from aiohttp import ClientSession
from pyatmo.auth import AbstractAsyncAuth
from homeassistant.helpers import config_entry_oauth2_flow

class HAModularAuth(AbstractAsyncAuth):
    def __init__(self, oauth_session: config_entry_oauth2_flow.OAuth2Session, session: ClientSession) -> None:
        self._oauth_session = oauth_session
        self._session = session
        self.websession = session
        self.base_url = "https://api.netatmo.com/"

    async def async_get_access_token(self) -> str:
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]

    async def async_make_api_request(self, method: str, url: str, data: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> bytes:
        token = await self.async_get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        if not url.startswith("http"):
            url = f"{self.base_url}{url.lstrip('/')}"
        async with self._session.request(method, url, headers=headers, json=data, params=params) as resp:
            resp.raise_for_status()
            return await resp.read()