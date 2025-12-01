"""Constantes pour l'intégration Mon Netatmo."""
from homeassistant.const import Platform

DOMAIN = "mon_netatmo"
PLATFORMS = [Platform.CLIMATE]

# Configuration Keys
CONF_URL = "url" # Pour l'override Cloudflare

# Netatmo Endpoints
OAUTH2_AUTHORIZE = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN = "https://api.netatmo.com/oauth2/token"

# Mapping Modes Netatmo <-> HA
# Netatmo: schedule, manual, away, hg (frost guard), off
NETATMO_MODE_SCHEDULE = "schedule"
NETATMO_MODE_MANUAL = "manual"
NETATMO_MODE_AWAY = "away"
NETATMO_MODE_HG = "hg"
NETATMO_MODE_OFF = "off"