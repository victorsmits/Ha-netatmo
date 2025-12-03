from typing import Any
import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

class AsyncConfigEntryAuth(pyatmo.auth.AbstractAsyncAuth):
    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session):
        self._session = session

    async def async_get_access_token(self) -> str:
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]

    async def async_post_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        params = kwargs.get("params")
        data = kwargs.get("data")
        json_payload = kwargs.get("json")

        if params and isinstance(params, dict):
            if "rooms" in params or "home" in params or "json" in params:
                json_payload = params.get("json", params)
                kwargs["params"] = None

        if data and isinstance(data, dict) and ("rooms" in data or "home" in data):
             json_payload = data
             kwargs["data"] = None

        if json_payload:
            kwargs["json"] = json_payload

        return await self._session.async_request("POST", url, **kwargs)

    async def async_get_api_request(self, endpoint: str, **kwargs: Any) -> Any:
        url = endpoint if endpoint.startswith("http") else f"https://api.netatmo.com/{endpoint}"
        return await self._session.async_request("GET", url, **kwargs)

class NetatmoDataHandler:
    def __init__(self, hass: HomeAssistant, session: config_entry_oauth2_flow.OAuth2Session):
        self.hass = hass
        self.session = session
        self.auth = AsyncConfigEntryAuth(session)
        self.account = pyatmo.AsyncAccount(self.auth)
        self.homes_data = {}

    async def async_update(self):
        await self.account.async_update_topology()
        for home_id in self.account.homes:
            try:
                await self.account.async_update_status(home_id)
            except Exception:
                pass
        self.homes_data = self.account.homes