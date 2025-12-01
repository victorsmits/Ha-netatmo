"""API Handler pour pyatmo."""
import logging
import pyatmo
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

_LOGGER = logging.getLogger(__name__)

class NetatmoDataHandler:
    """Gère les appels pyatmo pour tout le compte."""

    def __init__(self, hass: HomeAssistant, session: config_entry_oauth2_flow.OAuth2Session):
        self.hass = hass
        self.session = session
        self.account = pyatmo.AsyncAccount(self.session)
        self.homes_data = {}

    async def async_update(self):
        """Rafraîchir les données de toutes les maisons."""
        try:
            # update_topology met à jour la structure ET les états (températures, modes)
            await self.account.async_update_topology()
            self.homes_data = self.account.homes
        except Exception as err:
            _LOGGER.error("Erreur update Netatmo: %s", err)
            raise err