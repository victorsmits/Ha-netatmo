"""Config flow pour Netatmo Modular avec Options Persistantes."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_URL
from homeassistant.helpers import config_entry_oauth2_flow, network, selector
from homeassistant.core import callback

from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

_LOGGER = logging.getLogger(__name__)

class FixedUrlOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    def __init__(self, hass, domain, client_id, client_secret, authorize_url, token_url, fixed_url):
        super().__init__(hass, domain, client_id, client_secret, authorize_url, token_url)
        self._fixed_url = fixed_url

    @property
    def redirect_uri(self) -> str:
        base_url = self._fixed_url.rstrip("/")
        return f"{base_url}/auth/external/callback"

class NetatmoFlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    DOMAIN = DOMAIN
    
    @property
    def logger(self) -> logging.Logger:
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
        if user_input is not None:
            self.client_id = user_input[CONF_CLIENT_ID]
            self.client_secret = user_input[CONF_CLIENT_SECRET]
            custom_url = user_input.get(CONF_URL)
            
            if custom_url:
                implementation = FixedUrlOAuth2Implementation(
                    self.hass, self.DOMAIN, self.client_id, self.client_secret,
                    OAUTH2_AUTHORIZE, OAUTH2_TOKEN, custom_url
                )
            else:
                implementation = config_entry_oauth2_flow.LocalOAuth2Implementation(
                    self.hass, self.DOMAIN, self.client_id, self.client_secret,
                    OAUTH2_AUTHORIZE, OAUTH2_TOKEN
                )

            config_entry_oauth2_flow.async_register_implementation(
                self.hass, self.DOMAIN, implementation
            )
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NetatmoOptionsFlowHandler(config_entry)


class NetatmoOptionsFlowHandler(config_entries.OptionsFlow):
    """Gère la configuration (Options)."""

    def __init__(self, config_entry):
        # On ne stocke pas config_entry ici pour éviter l'erreur AttributeError
        self.selected_room_id = None

    async def async_step_init(self, user_input=None):
        """Etape 1 : Choix de la pièce."""
        rooms_dict = {}
        try:
            # Récupération sécurisée des données
            entry_id = self.config_entry.entry_id
            if DOMAIN in self.hass.data and entry_id in self.hass.data[DOMAIN]:
                data = self.hass.data[DOMAIN][entry_id]
                coordinator = data.get("coordinator")
                if coordinator:
                    for home_id, home in coordinator.data.items():
                        if home.rooms:
                            for r_id, room in home.rooms.items():
                                if hasattr(room, "name"):
                                    rooms_dict[r_id] = room.name
            
            if not rooms_dict:
                return self.async_abort(reason="no_rooms_found")
        except Exception:
            return self.async_abort(reason="integration_not_loaded")

        if user_input is not None:
            self.selected_room_id = user_input["room_id"]
            return await self.async_step_configure_room()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("room_id"): vol.In(rooms_dict)
            })
        )

    async def async_step_configure_room(self, user_input=None):
        """Etape 2 : Configuration des entités."""
        # On fait une COPIE explicite du dictionnaire pour éviter les problèmes de référence
        current_options = {k: v for k, v in self.config_entry.options.items()}
        rooms_config = dict(current_options.get("rooms_config", {}))
        
        # Récupération config existante pour pré-remplir
        room_config = rooms_config.get(self.selected_room_id, {})

        if user_input is not None:
            # Mise à jour
            rooms_config[self.selected_room_id] = {
                "sensor_entity": user_input.get("sensor_entity"),
                "input_number_entity": user_input.get("input_number_entity")
            }
            
            current_options["rooms_config"] = rooms_config
            
            # Sauvegarde : 'data' écrase les options existantes
            return self.async_create_entry(title="", data=current_options)

        # Formulaire
        schema = vol.Schema({
            vol.Optional("sensor_entity", description={"suggested_value": room_config.get("sensor_entity")}): 
                selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            
            vol.Optional("input_number_entity", description={"suggested_value": room_config.get("input_number_entity")}): 
                selector.EntitySelector(selector.EntitySelectorConfig(domain="input_number")),
        })

        return self.async_show_form(step_id="configure_room", data_schema=schema)