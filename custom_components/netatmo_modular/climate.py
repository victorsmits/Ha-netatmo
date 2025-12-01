"""Support Netatmo Fil Pilote via Pyatmo (Propre)."""
import logging
import time
from typing import Optional

from homeassistant.components.climate import (
    ClimateEntity, ClimateEntityFeature, HVACMode
)
from homeassistant.components.climate.const import (
    PRESET_AWAY, PRESET_ECO, PRESET_COMFORT, PRESET_NONE
)
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN, NETATMO_MODE_SCHEDULE, NETATMO_MODE_MANUAL, NETATMO_MODE_OFF

_LOGGER = logging.getLogger(__name__)

# Mapping des valeurs API
NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"
NETATMO_VAL_FROST_GUARD = "frost_guard"

# Durée du mode manuel (12h)
DEFAULT_MANUAL_DURATION = 43200 

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data_handler = hass.data[DOMAIN][entry.entry_id]
    
    async def async_update_data():
        await data_handler.async_update()
        return data_handler.homes_data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="netatmo_climate_clean", update_method=async_update_data
    )
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for home_id, home in coordinator.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
            if hasattr(room, "name"):
                entities.append(NetatmoRoomFilPilote(coordinator, home_id, room_id, data_handler))
            
    async_add_entities(entities)


class NetatmoRoomFilPilote(CoordinatorEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, home_id, room_id, data_handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._handler = data_handler
        self._attr_unique_id = f"{home_id}-{room_id}-clean"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name

    @property
    def _room_data(self):
        try: return self.coordinator.data[self._home_id].rooms[self._room_id]
        except: return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Mode HA (Heat, Auto, Off)."""
        room = self._room_data
        if not room: return HVACMode.OFF
        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        if mode == NETATMO_MODE_SCHEDULE or mode == "home": return HVACMode.AUTO
        if mode == NETATMO_MODE_OFF: return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> Optional[str]:
        """Mode HA (Confort, Eco, Away)."""
        room = self._room_data
        if not room: return PRESET_NONE
        
        # Si on est en planning, pas de preset
        mode_global = getattr(room, "therm_setpoint_mode", None)
        if mode_global == NETATMO_MODE_SCHEDULE or mode_global == "home": return PRESET_NONE

        # Lecture valeur brute
        fp_val = getattr(room, "therm_setpoint_fp", None)
        if fp_val == NETATMO_VAL_COMFORT: return PRESET_COMFORT
        if fp_val == NETATMO_VAL_ECO_MAPPED: return PRESET_ECO
        if fp_val == NETATMO_VAL_FROST_GUARD: return PRESET_AWAY 
        return PRESET_NONE

    async def _async_set_state_pyatmo(self, mode_name, fp_val=None):
        """Utilise la fonction officielle de pyatmo."""
        try:
            # On récupère l'objet Home de pyatmo
            home = self._handler.account.homes[self._home_id]
            
            # On construit le dictionnaire de la pièce
            room_payload = {
                "id": self._room_id,
                "therm_setpoint_mode": mode_name
            }
            
            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val:
                    room_payload["therm_setpoint_fp"] = fp_val
                # Ajout du temps obligatoire
                room_payload["therm_setpoint_end_time"] = int(time.time() + DEFAULT_MANUAL_DURATION)

            # Pyatmo s'attend à recevoir un dictionnaire qu'il va fusionner
            # La méthode s'appelle async_set_state({'rooms': [...]})
            _LOGGER.info(f"Appel Pyatmo pour {self._attr_name} : {room_payload}")
            
            await home.async_set_state({"rooms": [room_payload]})
            
            # Rafraîchissement des données
            await self.coordinator.async_request_refresh()
            
        except Exception as e:
            _LOGGER.error(f"Erreur Pyatmo: {e}")
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

        if hvac_mode == HVACMode.OFF:
            await self._async_set_state_pyatmo(NETATMO_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_set_state_pyatmo("home")
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_set_state_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_COMFORT)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._attr_preset_mode = preset_mode
        self._attr_hvac_mode = HVACMode.HEAT
        self.async_write_ha_state()

        if preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return

        target = None
        if preset_mode == PRESET_COMFORT: target = NETATMO_VAL_COMFORT
        elif preset_mode == PRESET_ECO: target = NETATMO_VAL_ECO_MAPPED 
        elif preset_mode == PRESET_AWAY: target = NETATMO_VAL_FROST_GUARD

        if target:
            await self._async_set_state_pyatmo(NETATMO_MODE_MANUAL, target)