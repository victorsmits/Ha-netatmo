from typing import Final

DOMAIN: Final = "netatmo_modular"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_EXTERNAL_URL: Final = "external_url"

OAUTH2_AUTHORIZE: Final = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN: Final = "https://api.netatmo.com/oauth2/token"

SCOPES: Final = [
    "read_thermostat", "write_thermostat", "read_station", 
    "read_camera", "access_camera", "write_camera", "read_presence", 
    "access_presence", "read_homecoach", "read_smokedetector", 
    "read_doorbell", "access_doorbell", "read_smarther", 
    "write_smarther", "read_bubendorff", "write_bubendorff", 
    "read_mx", "write_mx", "read_mhs1", "write_mhs1"
]

API_BASE_URL: Final = "https://api.netatmo.com/api"
UPDATE_INTERVAL: Final = 60

PRESET_SCHEDULE: Final = "schedule"
PRESET_MANUAL: Final = "manual"
PRESET_AWAY: Final = "away"
PRESET_FROST_GUARD: Final = "frost_guard"

PRESET_MODES: Final = [
    PRESET_SCHEDULE,
    PRESET_MANUAL,
    PRESET_AWAY,
    PRESET_FROST_GUARD,
]

NETATMO_TO_PRESET_MAP: Final[dict[str, str]] = {
    "schedule": PRESET_SCHEDULE,
    "home": PRESET_SCHEDULE,
    "manual": PRESET_MANUAL,
    "away": PRESET_AWAY,
    "hg": PRESET_FROST_GUARD,
    "frost_guard": PRESET_FROST_GUARD,
}

PRESET_TO_NETATMO_MAP: Final[dict[str, str]] = {
    PRESET_SCHEDULE: "home",
    PRESET_MANUAL: "manual",
    PRESET_AWAY: "away",
    PRESET_FROST_GUARD: "hg",
}

SUPPORTED_LIGHT_TYPES: Final = [
    "NLL", "NLF", "NLFN", "NLV", "NLLV", 
    "NLLM", "NLM", "NLFE", "NLP",
]

MIN_TEMP: Final = 7
MAX_TEMP: Final = 30
TEMP_STEP: Final = 0.5