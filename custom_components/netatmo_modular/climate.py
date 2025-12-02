"""Support Netatmo Fil Pilote - Centralized Polling."""
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, 
    NETATMO_MODE_SCHEDULE, 
    NETATMO_MODE_MANUAL, 
    NETATMO_MODE_OFF,
    NETATMO_MODE_AWAY,
    NETATMO_MODE_HG
)

_LOGGER = logging.getLogger(__name__)

# --- VALEURS API ---
NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"
NETATMO_VAL_FROST_GUARD = "frost_guard"

DEFAULT_MANUAL_DURATION = 43200 

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Setup entities using the central coordinator."""
    # Récupération du contexte global créé dans __init__.py
    data_context = hass.data[DOMAIN][entry.entry_id]
    
    coordinator = data_context["coordinator"]
    data_handler = data_context["api"]

    entities = []
    # coordinator.data contient déjà les homes_data
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
        
        self._attr_unique_id = f"{home_id}-{room_id}"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name
        
        # Initialisation de l'état
        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model="Sortie de Câble Connectée",
            suggested_area=self._attr_name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Mise à jour des données depuis le coordinateur central."""
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        try:
            room = self.coordinator.data[self._home_id].rooms[self._room_id]
        except (KeyError, AttributeError):
            return

        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        fp_val = getattr(room, "therm_setpoint_fp", None)

        if mode == NETATMO_MODE_OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_NONE
        elif mode == NETATMO_MODE_SCHEDULE or mode == "home":
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE
        elif mode == NETATMO_MODE_HG:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_AWAY
        elif mode == NETATMO_MODE_AWAY:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_ECO
        elif mode == NETATMO_MODE_MANUAL:
            self._attr_hvac_mode = HVACMode.HEAT
            if fp_val == NETATMO_VAL_ECO_MAPPED:
                self._attr_preset_mode = PRESET_ECO
            elif fp_val == NETATMO_VAL_FROST_GUARD:
                self._attr_preset_mode = PRESET_AWAY
            elif fp_val == NETATMO_VAL_COMFORT:
                self._attr_preset_mode = PRESET_COMFORT
            else:
                if self._attr_preset_mode == PRESET_NONE:
                    self._attr_preset_mode = PRESET_COMFORT
        else:
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE

    async def _async_push_pyatmo(self, mode_name, fp_val=None):
        try:
            home = self._handler.account.homes[self._home_id]
            room_payload = {"id": self._room_id, "therm_setpoint_mode": mode_name}
            
            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val: room_payload["therm_setpoint_fp"] = fp_val
                room_payload["therm_setpoint_end_time"] = int(time.time() + DEFAULT_MANUAL_DURATION)

            _LOGGER.debug(f"Commande envoyée: {room_payload}")
            await home.async_set_state({"rooms": [room_payload]})
            
        except Exception as e:
            _LOGGER.error(f"Erreur envoi commande: {e}")
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT: self._attr_preset_mode = PRESET_NONE
        self.async_write_ha_state()

        if hvac_mode == HVACMode.OFF:
            await self._async_push_pyatmo(NETATMO_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_push_pyatmo("home")
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_COMFORT)

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
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, target)