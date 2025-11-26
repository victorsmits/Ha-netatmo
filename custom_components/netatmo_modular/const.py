"""Constants for Netatmo Modular integration."""
from typing import Final
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_SLEEP,
)

DOMAIN: Final = "netatmo_modular"

# Configuration keys
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_EXTERNAL_URL: Final = "external_url"

# OAuth2
OAUTH2_AUTHORIZE: Final = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN: Final = "https://api.netatmo.com/oauth2/token"

# Scopes (Votre liste complète)
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

# Update intervals (Polling de secours)
UPDATE_INTERVAL: Final = 60

# Mappings
# Netatmo -> HA Preset
NETATMO_TO_PRESET_MAP: Final[dict[str, str]] = {
    "comfort": PRESET_COMFORT,
    "frost_guard": PRESET_SLEEP, # Lit
    "hg": PRESET_SLEEP,          # Lit
    "away": PRESET_AWAY,
    "schedule": PRESET_HOME,     # Maison
    "home": PRESET_HOME,         # Maison
    "eco": PRESET_AWAY,          # Eco -> Away
}

# HA Preset -> Netatmo Command
PRESET_TO_NETATMO_MAP: Final[dict[str, str]] = {
    PRESET_HOME: "schedule",
    PRESET_AWAY: "away",
    PRESET_SLEEP: "frost_guard",
    PRESET_COMFORT: "comfort",
}

PRESET_MODES: Final = [
    PRESET_COMFORT,
    PRESET_SLEEP, 
    PRESET_AWAY,
    PRESET_HOME,
]

# Supported Light Types (Codes API)
SUPPORTED_LIGHT_TYPES: Final = {
    "NLL", "NLF", "NLFN", "NLV", "NLLV", "NLLM", "NLM", "NLC", "NLP", "NLFE", "Z3L"
}

# Dimmer Types
DIMMER_TYPES: Final = {
    "NLF", "NLFN", "NLV", "NLLV", "NLFE", "Z3L"
}

# Attributes
ATTR_HOME_ID: Final = "home_id"
ATTR_ROOM_ID: Final = "room_id"
ATTR_MODULE_ID: Final = "module_id"
ATTR_BATTERY_LEVEL: Final = "battery_level"
ATTR_RF_STRENGTH: Final = "rf_strength"
ATTR_FIL_PILOTE: Final = "fil_pilote"