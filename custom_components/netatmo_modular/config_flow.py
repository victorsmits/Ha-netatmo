import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_URL
from homeassistant.helpers import config_entry_oauth2_flow, network
from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

class FixedUrlOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    def __init__(self, hass, domain, client_id, client_secret, authorize_url, token_url, fixed_url):
        super().__init__(hass, domain, client_id, client_secret, authorize_url, token_url)
        self._fixed_url = fixed_url

    @property
    def redirect_uri(self) -> str:
        return f"{self._fixed_url.rstrip('/')}/auth/external/callback"

class NetatmoFlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    DOMAIN = DOMAIN

    @property
    def logger(self):
        import logging
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict:
        scopes = [
            "read_thermostat", "write_thermostat", "read_station", "read_camera",
            "write_camera", "access_camera", "read_doorbell", "access_doorbell",
            "read_presence", "access_presence", "read_homecoach", "read_smokedetector",
            "read_magellan", "write_magellan", "read_bubendorff", "write_bubendorff",
            "read_smarther", "write_smarther", "read_mx", "write_mx",
            "write_presence", "read_carbonmonoxidedetector", "read_mhs1", "write_mhs1"
        ]
        return {"scope": " ".join(scopes)}

    async def async_step_user(self, user_input=None):
        if user_input:
            self.client_id = user_input[CONF_CLIENT_ID]
            self.client_secret = user_input[CONF_CLIENT_SECRET]
            custom_url = user_input.get(CONF_URL)
            
            if custom_url:
                impl = FixedUrlOAuth2Implementation(
                    self.hass, self.DOMAIN, self.client_id, self.client_secret,
                    OAUTH2_AUTHORIZE, OAUTH2_TOKEN, custom_url
                )
            else:
                impl = config_entry_oauth2_flow.LocalOAuth2Implementation(
                    self.hass, self.DOMAIN, self.client_id, self.client_secret,
                    OAUTH2_AUTHORIZE, OAUTH2_TOKEN
                )

            config_entry_oauth2_flow.async_register_implementation(self.hass, self.DOMAIN, impl)
            return await self.async_step_pick_implementation()

        try:
            default_url = network.get_url(self.hass, allow_internal=False, allow_ip=False)
        except network.NoURLAvailableError:
            default_url = ""

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Optional(CONF_URL, description={"suggested_value": default_url}): str,
            })
        )

    async def async_oauth_create_entry(self, data: dict) -> config_entries.ConfigEntry:
        data[CONF_CLIENT_ID] = self.client_id
        data[CONF_CLIENT_SECRET] = self.client_secret
        return await super().async_oauth_create_entry(data)