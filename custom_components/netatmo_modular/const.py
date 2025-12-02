"""Constantes."""
from homeassistant.const import Platform

DOMAIN = "netatmo_modular"
PLATFORMS = [Platform.CLIMATE]

CONF_URL = "url" 
OAUTH2_AUTHORIZE = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN = "https://api.netatmo.com/oauth2/token"

# Modes API
NETATMO_MODE_SCHEDULE = "schedule"
NETATMO_MODE_MANUAL = "manual"
NETATMO_MODE_OFF = "off"
NETATMO_MODE_AWAY = "away"
NETATMO_MODE_HG = "hg"