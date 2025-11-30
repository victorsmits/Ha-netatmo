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

# Update intervals
UPDATE_INTERVAL: Final = 300

# API Netatmo Values
NETATMO_API_SCHEDULE: Final = "schedule"
NETATMO_API_MANUAL: Final = "manual"
NETATMO_API_AWAY: Final = "away"
NETATMO_API_HG: Final = "hg"
NETATMO_API_FROST_GUARD: Final = "frost_guard"
NETATMO_API_HOME: Final = "home"

# Custom HA Presets
PRESET_SCHEDULE: Final = "home"
PRESET_MANUAL: Final = "manual"
PRESET_FROST_GUARD: Final = "frost_guard"

# Liste NETTOYÉE des modes disponibles dans l'UI
# On retire Comfort et Eco qui créent des doublons inutiles pour les pièces
PRESET_MODES: Final = [
    PRESET_SCHEDULE, # Planning
    PRESET_MANUAL,   # Manuel
    PRESET_AWAY,     # Absent
    PRESET_FROST_GUARD, # Hors-gel
]

# Mapping Netatmo (API) -> HA Preset
NETATMO_TO_PRESET_MAP: Final[dict[str, str]] = {
    NETATMO_API_SCHEDULE: PRESET_SCHEDULE,
    NETATMO_API_HOME: PRESET_SCHEDULE,
    NETATMO_API_MANUAL: PRESET_MANUAL,
    NETATMO_API_AWAY: PRESET_AWAY,
    NETATMO_API_HG: PRESET_FROST_GUARD,
    NETATMO_API_FROST_GUARD: PRESET_FROST_GUARD,
}

# Mapping HA Preset -> Netatmo (API)
PRESET_TO_NETATMO_MAP: Final[dict[str, str]] = {
    PRESET_SCHEDULE: NETATMO_API_HOME,
    PRESET_MANUAL: NETATMO_API_MANUAL,
    PRESET_AWAY: NETATMO_API_AWAY,
    PRESET_FROST_GUARD: NETATMO_API_HG,
}

# Device Types
DEVICE_TYPE_THERMOSTAT: Final = "NATherm1"
DEVICE_TYPE_VALVE: Final = "NRV"
DEVICE_TYPE_PLUG: Final = "NAPlug"
DEVICE_TYPE_OTH: Final = "OTH"
DEVICE_TYPE_OTM: Final = "OTM"
DEVICE_TYPE_BNS: Final = "BNS"

# Light Types
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