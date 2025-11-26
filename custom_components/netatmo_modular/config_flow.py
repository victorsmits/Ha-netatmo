"""Config flow for Netatmo Modular integration."""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
    SCOPES,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EXTERNAL_URL,
)

_LOGGER = logging.getLogger(__name__)

CONF_AUTH_CODE = "auth_code"

class NetatmoModularConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Netatmo Modular."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Get credentials and external URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_CLIENT_ID] = user_input[CONF_CLIENT_ID].strip()
            self._data[CONF_CLIENT_SECRET] = user_input[CONF_CLIENT_SECRET].strip()
            self._data[CONF_EXTERNAL_URL] = user_input.get(CONF_EXTERNAL_URL, "").strip()
            
            if not self._data[CONF_CLIENT_ID]:
                errors[CONF_CLIENT_ID] = "invalid_client_id"
            elif not self._data[CONF_CLIENT_SECRET]:
                errors[CONF_CLIENT_SECRET] = "invalid_client_secret"
            else:
                return await self.async_step_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                    vol.Required(CONF_EXTERNAL_URL, default="https://ha.victorsmits.com"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: OAuth authorization."""
        errors: dict[str, str] = {}
        
        external_url = self._data.get(CONF_EXTERNAL_URL, "").rstrip("/")
        if external_url:
            callback_url = f"{external_url}/auth/external/callback"
        else:
            callback_url = "https://my.home-assistant.io/redirect/oauth"
        
        if user_input is not None:
            auth_code = user_input.get(CONF_AUTH_CODE, "").strip()
            
            if not auth_code:
                errors[CONF_AUTH_CODE] = "missing_code"
            else:
                try:
                    tokens = await self._async_exchange_code(auth_code, callback_url)
                    
                    self._data["token"] = {
                        "access_token": tokens["access_token"],
                        "refresh_token": tokens["refresh_token"],
                        "expires_at": tokens.get("expires_at"), # Déjà en timestamp float grâce à _async_exchange_code
                        "scope": tokens.get("scope"),
                    }
                    
                    await self.async_set_unique_id(f"netatmo_{self._data[CONF_CLIENT_ID][:8]}")
                    self._abort_if_unique_id_configured()
                    
                    return self.async_create_entry(
                        title="Netatmo Modular",
                        data=self._data,
                    )
                    
                except Exception as err:
                    _LOGGER.error("Token exchange failed: %s", err)
                    errors["base"] = "invalid_auth"

        auth_params = {
            "client_id": self._data[CONF_CLIENT_ID],
            "redirect_uri": callback_url,
            "scope": " ".join(SCOPES),
            "state": "netatmo_ha_auth",
        }
        
        auth_url = f"{OAUTH2_AUTHORIZE}?{urllib.parse.urlencode(auth_params)}"
        
        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AUTH_CODE): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "auth_url": auth_url,
                "callback_url": callback_url,
            },
        )

    async def _async_exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        session = async_get_clientsession(self.hass)

        data = {
            "grant_type": "authorization_code",
            "client_id": self._data[CONF_CLIENT_ID],
            "client_secret": self._data[CONF_CLIENT_SECRET],
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
        }

        async with session.post(OAUTH2_TOKEN, data=data) as response:
            response_text = await response.text()
            
            if response.status != 200:
                _LOGGER.error("Token exchange failed: %s", response_text)
                raise Exception(f"Token exchange failed: {response_text}")

            try:
                result = await response.json()
            except Exception:
                import json
                result = json.loads(response_text)

            # CORRECTIF : Conversion immédiate en timestamp (float)
            if "expires_at" not in result and "expires_in" in result:
                expires_at = datetime.now() + timedelta(seconds=result["expires_in"])
                result["expires_at"] = expires_at.timestamp()

            return result