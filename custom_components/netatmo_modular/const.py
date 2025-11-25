"""Constants for Netatmo Modular integration."""
from typing import Final
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_SLEEP, # On importe SLEEP pour le lit
)

DOMAIN: Final = "netatmo_modular"

# Configuration keys
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_EXTERNAL_URL: Final = "external_url"

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
]

# API Endpoints
API_BASE_URL: Final = "https://api.netatmo.com/api"
API_HOMES_DATA: Final = f"{API_BASE_URL}/homesdata"
API_HOME_STATUS: Final = f"{API_BASE_URL}/homestatus"
API_SET_ROOM_THERMPOINT: Final = f"{API_BASE_URL}/setroomthermpoint"
API_SET_THERM_MODE: Final = f"{API_BASE_URL}/setthermmode"
API_SET_STATE: Final = f"{API_BASE_URL}/setstate"

# Update intervals
UPDATE_INTERVAL: Final = 300
TOKEN_REFRESH_BUFFER: Final = 600

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

# Netatmo preset modes (Interne)
NETATMO_PRESET_COMFORT: Final = "comfort"
NETATMO_PRESET_FROST_GUARD: Final = "frost_guard"
NETATMO_PRESET_AWAY: Final = "away"
NETATMO_PRESET_SCHEDULE: Final = "schedule"

# HA preset modes mapping
# On utilise SLEEP (Lit) pour le Hors-Gel
PRESET_MODES: Final = [
    PRESET_COMFORT,
    PRESET_SLEEP, 
    PRESET_AWAY,
    PRESET_HOME,
]

# Device types
DEVICE_TYPE_THERMOSTAT: Final = "NATherm1"
DEVICE_TYPE_VALVE: Final = "NRV"
DEVICE_TYPE_PLUG: Final = "NAPlug"
DEVICE_TYPE_OTH: Final = "OTH"
DEVICE_TYPE_OTM: Final = "OTM"
DEVICE_TYPE_BNS: Final = "BNS"

# Supported device types
SUPPORTED_CLIMATE_TYPES: Final = [
    DEVICE_TYPE_THERMOSTAT,
    DEVICE_TYPE_VALVE,
    DEVICE_TYPE_PLUG,
    DEVICE_TYPE_OTH,
    DEVICE_TYPE_OTM,
    DEVICE_TYPE_BNS,
]

# Temperature limits
MIN_TEMP: Final = 7
MAX_TEMP: Final = 30
TEMP_STEP: Final = 0.5

# Attributes
ATTR_HOME_ID: Final = "home_id"
ATTR_ROOM_ID: Final = "room_id"
ATTR_MODULE_ID: Final = "module_id"
ATTR_BATTERY_LEVEL: Final = "battery_level"
ATTR_RF_STRENGTH: Final = "rf_strength"
ATTR_BOILER_STATUS: Final = "boiler_status"
ATTR_HEATING_POWER_REQUEST: Final = "heating_power_request"
ATTR_ANTICIPATING: Final = "anticipating"
ATTR_OPEN_WINDOW: Final = "open_window"