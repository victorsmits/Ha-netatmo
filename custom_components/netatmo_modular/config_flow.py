"""Config flow for Netatmo Modular integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
    SCOPES,
)

_LOGGER = logging.getLogger(__name__)


class NetatmoModularOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle a config flow for Netatmo Modular."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._client_id: str | None = None
        self._client_secret: str | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": " ".join(SCOPES)}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]

            # Validate credentials by testing the OAuth2 flow
            try:
                # Store credentials temporarily for the OAuth2 flow
                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN]["temp_credentials"] = {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                }

                # Register the OAuth2 implementation
                config_entry_oauth2_flow.async_register_implementation(
                    self.hass,
                    DOMAIN,
                    NetatmoOAuth2Implementation(
                        self.hass,
                        DOMAIN,
                        self._client_id,
                        self._client_secret,
                    ),
                )

                return await self.async_step_pick_implementation()

            except Exception as err:
                _LOGGER.exception("Error setting up OAuth2: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "netatmo_dev_url": "https://dev.netatmo.com/apps",
            },
        )

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> FlowResult:
        """Create an entry for the flow."""
        # Get the credentials we stored earlier
        temp_creds = self.hass.data.get(DOMAIN, {}).get("temp_credentials", {})

        # Add client credentials to the token data
        data["client_id"] = temp_creds.get("client_id", self._client_id)
        data["client_secret"] = temp_creds.get("client_secret", self._client_secret)

        # Clean up temp credentials
        if DOMAIN in self.hass.data and "temp_credentials" in self.hass.data[DOMAIN]:
            del self.hass.data[DOMAIN]["temp_credentials"]

        # Check if already configured
        existing_entry = await self.async_set_unique_id(f"netatmo_modular_{data['client_id'][:8]}")
        if existing_entry:
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title="Netatmo Modular",
            data=data,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle re-authentication."""
        self._client_id = entry_data.get("client_id")
        self._client_secret = entry_data.get("client_secret")

        if self._client_id and self._client_secret:
            # Re-register OAuth2 implementation
            config_entry_oauth2_flow.async_register_implementation(
                self.hass,
                DOMAIN,
                NetatmoOAuth2Implementation(
                    self.hass,
                    DOMAIN,
                    self._client_id,
                    self._client_secret,
                ),
            )
            return await self.async_step_pick_implementation()

        return await self.async_step_user()


class NetatmoOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """Netatmo OAuth2 implementation."""

    def __init__(
        self,
        hass,
        domain: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Initialize the OAuth2 implementation."""
        super().__init__(
            hass,
            domain,
            client_id,
            client_secret,
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        )

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data for authorization."""
        return {"scope": " ".join(SCOPES)}

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Resolve external data to tokens."""
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": external_data["code"],
                "redirect_uri": external_data["state"]["redirect_uri"],
            }
        )

    async def _async_refresh_token(self, token: dict) -> dict:
        """Refresh the access token."""
        new_token = await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
            }
        )
        return {**token, **new_token}

    async def _token_request(self, data: dict) -> dict:
        """Make a token request."""
        session = async_get_clientsession(self.hass)

        data["client_id"] = self.client_id
        data["client_secret"] = self.client_secret

        _LOGGER.debug("Token request: %s", {k: v for k, v in data.items() if k != "client_secret"})

        async with session.post(self.token_url, data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Token request failed: %s - %s", response.status, error_text)
                raise Exception(f"Token request failed: {error_text}")

            result = await response.json()

            # Add expires_at if not present
            if "expires_at" not in result and "expires_in" in result:
                result["expires_at"] = (
                    datetime.now() + timedelta(seconds=result["expires_in"])
                ).timestamp()

            return result
