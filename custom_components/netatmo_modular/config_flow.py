"""Config flow for Netatmo Modular integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
    SCOPES,
    CONF_EXTERNAL_URL,
)

_LOGGER = logging.getLogger(__name__)


def get_callback_url(hass: HomeAssistant, external_url: str | None = None) -> str:
    """Get the OAuth callback URL."""
    if external_url:
        # Use user-provided external URL (Cloudflare)
        return f"{external_url.rstrip('/')}/auth/external/callback"
    
    # Try to get the external URL from HA config
    try:
        base_url = get_url(hass, allow_internal=False, prefer_external=True)
        return f"{base_url}/auth/external/callback"
    except Exception:
        pass
    
    # Fallback to my.home-assistant.io
    return "https://my.home-assistant.io/redirect/oauth"


class NetatmoModularConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Netatmo Modular."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._external_url: str | None = None
        self._auth_code: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - get credentials and external URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]
            self._external_url = user_input.get(CONF_EXTERNAL_URL, "").strip() or None

            # Validate that we can build a callback URL
            callback_url = get_callback_url(self.hass, self._external_url)
            
            # Store for later
            self.hass.data.setdefault(DOMAIN, {})
            self.hass.data[DOMAIN]["temp_config"] = {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "external_url": self._external_url,
                "callback_url": callback_url,
            }

            return await self.async_step_auth()

        # Default external URL hint
        default_external_url = ""
        try:
            default_external_url = get_url(self.hass, allow_internal=False, prefer_external=True)
        except Exception:
            pass

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                    vol.Optional(CONF_EXTERNAL_URL, default=default_external_url): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "netatmo_dev_url": "https://dev.netatmo.com/apps",
            },
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the OAuth authorization step."""
        errors: dict[str, str] = {}
        
        temp_config = self.hass.data.get(DOMAIN, {}).get("temp_config", {})
        callback_url = temp_config.get("callback_url", "")
        
        if user_input is not None:
            # User provided the authorization code
            auth_code = user_input.get("auth_code", "").strip()
            
            if auth_code:
                # Exchange the code for tokens
                try:
                    tokens = await self._exchange_code_for_tokens(auth_code, callback_url)
                    
                    # Create the config entry
                    return self.async_create_entry(
                        title="Netatmo Modular",
                        data={
                            "client_id": self._client_id,
                            "client_secret": self._client_secret,
                            "external_url": self._external_url,
                            "token": {
                                "access_token": tokens["access_token"],
                                "refresh_token": tokens["refresh_token"],
                                "expires_at": tokens.get("expires_at"),
                            },
                        },
                    )
                except Exception as err:
                    _LOGGER.error("Failed to exchange code for tokens: %s", err)
                    errors["base"] = "invalid_auth"

        # Build the authorization URL
        auth_params = {
            "client_id": self._client_id,
            "redirect_uri": callback_url,
            "scope": " ".join(SCOPES),
            "state": "netatmo_modular_auth",
        }
        auth_url = f"{OAUTH2_AUTHORIZE}?{'&'.join(f'{k}={v}' for k, v in auth_params.items())}"

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_code"): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "auth_url": auth_url,
                "callback_url": callback_url,
            },
        )

    async def _exchange_code_for_tokens(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for tokens."""
        session = async_get_clientsession(self.hass)

        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
        }

        _LOGGER.debug("Exchanging code for tokens with redirect_uri: %s", redirect_uri)

        async with session.post(OAUTH2_TOKEN, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Token exchange failed: %s - %s", response.status, error_text)
                raise Exception(f"Token exchange failed: {error_text}")

            result = await response.json()

            # Calculate expires_at
            if "expires_at" not in result and "expires_in" in result:
                result["expires_at"] = (
                    datetime.now() + timedelta(seconds=result["expires_in"])
                ).isoformat()

            _LOGGER.info("Successfully obtained Netatmo tokens")
            return result

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle re-authentication."""
        self._client_id = entry_data.get("client_id")
        self._client_secret = entry_data.get("client_secret")
        self._external_url = entry_data.get("external_url")

        # Store for the auth step
        callback_url = get_callback_url(self.hass, self._external_url)
        self.hass.data.setdefault(DOMAIN, {})
        self.hass.data[DOMAIN]["temp_config"] = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "external_url": self._external_url,
            "callback_url": callback_url,
        }

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication confirmation."""
        if user_input is not None:
            return await self.async_step_auth()

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={
                "client_id": self._client_id[:8] + "..." if self._client_id else "N/A",
            },
        )
