"""Constants for Netatmo Modular integration."""
from typing import Final
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_SLEEP,
)

DOMAIN: Final = "netatmo_modular"

# Configuration keys
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_EXTERNAL_URL: Final = "external_url"
CONF_WEBHOOK_ID: Final = "webhook_id"

# OAuth2
OAUTH2_AUTHORIZE: Final = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN: Final = "https://api.netatmo.com/oauth2/token"

# Scopes
SCOPES: Final = [
    "read_thermostat",
    "write_thermostat",
    "read_station",
    "read_camera",
    "write_camera",
    "access_camera",
    "read_doorbell",
    "access_doorbell",
    "read_presence",
    "access_presence",
    "read_homecoach",
    "read_smokedetector",
    "read_magellan",
    "write_magellan",
    "read_bubendorff",
    "write_bubendorff",
    "read_smarther",
    "write_smarther",
    "read_mx",
    "write_mx",
    "write_presence",
    "read_carbonmonoxidedetector",
    "read_mhs1",
    "write_mhs1"
]

# API Endpoints
API_BASE_URL: Final = "https://api.netatmo.com/api"

# Update intervals - 60 Secondes pour être réactif
UPDATE_INTERVAL: Final = 60

# Netatmo thermostat modes mapping
NETATMO_TO_HA_HVAC_MODE: Final = {
    "schedule": "auto",
    "away": "off",
    "hg": "off",
    "frost_guard": "off",
    "manual": "heat",
    "off": "off",
    "max": "heat",
}

HA_TO_NETATMO_HVAC_MODE: Final = {
    "auto": "schedule",
    "heat": "manual",
    "off": "away",
}

# Netatmo preset modes
NETATMO_PRESET_COMFORT: Final = "comfort"
NETATMO_PRESET_FROST_GUARD: Final = "frost_guard"
NETATMO_PRESET_AWAY: Final = "away"
NETATMO_PRESET_SCHEDULE: Final = "home"
NETATMO_PRESET_ECO: Final = "eco"

# Mappings
NETATMO_TO_PRESET_MAP: Final[dict[str, str]] = {
    NETATMO_PRESET_COMFORT: PRESET_COMFORT,
    NETATMO_PRESET_FROST_GUARD: PRESET_SLEEP,
    "hg": PRESET_SLEEP,
    NETATMO_PRESET_AWAY: PRESET_AWAY,
    NETATMO_PRESET_SCHEDULE: PRESET_HOME,
    "schedule": PRESET_HOME,
    NETATMO_PRESET_ECO: PRESET_AWAY,
}

PRESET_TO_NETATMO_MAP: Final[dict[str, str]] = {
    PRESET_HOME: NETATMO_PRESET_SCHEDULE,
    PRESET_AWAY: NETATMO_PRESET_AWAY,
    PRESET_SLEEP: NETATMO_PRESET_FROST_GUARD,
    PRESET_COMFORT: NETATMO_PRESET_COMFORT,
    PRESET_ECO: NETATMO_PRESET_FROST_GUARD, 
}

PRESET_MODES: Final = [
    PRESET_COMFORT,
    PRESET_SLEEP, 
    PRESET_AWAY,
    PRESET_HOME,
]

# --- DEVICE TYPES ---
DEVICE_TYPE_THERMOSTAT: Final = "NATherm1"
DEVICE_TYPE_VALVE: Final = "NRV"
DEVICE_TYPE_PLUG: Final = "NAPlug"
DEVICE_TYPE_OTH: Final = "OTH"
DEVICE_TYPE_OTM: Final = "OTM"
DEVICE_TYPE_BNS: Final = "BNS"

# Light Types (Legrand/Netatmo)
DEVICE_TYPE_LIGHT: Final = "NLL"
DEVICE_TYPE_DIMMER: Final = "NLF"
DEVICE_TYPE_DIMMER2: Final = "NLFN"
DEVICE_TYPE_DIMMER_NO_NEUTRAL: Final = "NLV"
DEVICE_TYPE_DIMMER_MICRO: Final = "NLLV"
DEVICE_TYPE_MICROMODULE: Final = "NLLM"
DEVICE_TYPE_MICROMODULE_2: Final = "NLM"
DEVICE_TYPE_DIMMER_FLAT: Final = "NLFE"
DEVICE_TYPE_PLUG_LIGHT: Final = "NLP"

SUPPORTED_LIGHT_TYPES: Final = [
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_DIMMER,
    DEVICE_TYPE_DIMMER2,
    DEVICE_TYPE_DIMMER_NO_NEUTRAL,
    DEVICE_TYPE_DIMMER_MICRO,
    DEVICE_TYPE_MICROMODULE,
    DEVICE_TYPE_MICROMODULE_2,
    DEVICE_TYPE_DIMMER_FLAT,
    DEVICE_TYPE_PLUG_LIGHT,
]

# Temperature limits
MIN_TEMP: Final = 7
MAX_TEMP: Final = 30
TEMP_STEP: Final = 0.5