"""Constantes pour l'intégration Mon Netatmo."""
from homeassistant.const import Platform

# DOIT CORRESPONDRE AU NOM DU DOSSIER
DOMAIN = "netatmo_modular"
PLATFORMS = [Platform.CLIMATE]

CONF_URL = "url" 

# Endpoints OAuth
OAUTH2_AUTHORIZE = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN = "https://api.netatmo.com/oauth2/token"

# Constantes utilisées par climate.py (C'est ça qui manquait surement)
NETATMO_MODE_SCHEDULE = "schedule"
NETATMO_MODE_MANUAL = "manual"
NETATMO_MODE_OFF = "off"
NETATMO_MODE_AWAY = "away"
NETATMO_MODE_HG = "hg"