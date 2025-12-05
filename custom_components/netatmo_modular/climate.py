"""Support Netatmo Fil Pilote - HYBRIDE (Config UI + Fallback Auto)."""
import logging
import time
from datetime import timedelta

from homeassistant.util import slugify 
from homeassistant.components.climate import (
    ClimateEntity, ClimateEntityFeature, HVACMode
)
from homeassistant.components.climate.const import (
    PRESET_AWAY, PRESET_ECO, PRESET_COMFORT, PRESET_NONE
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, NETATMO_MODE_SCHEDULE, NETATMO_MODE_MANUAL, NETATMO_MODE_OFF, NETATMO_MODE_AWAY, NETATMO_MODE_HG

_LOGGER = logging.getLogger(__name__)

NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"
NETATMO_VAL_FROST_GUARD = "frost_guard"
DEFAULT_MANUAL_DURATION = 43200 

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data_context = hass.data[DOMAIN][entry.entry_id]
    coordinator = data_context["coordinator"]
    data_handler = data_context["api"]
    
    # Options
    rooms_config = entry.options.get("rooms_config", {})

    entities = []
    for home_id, home in coordinator.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
            if hasattr(room, "name"):
                is_radiator = False
                if hasattr(room, "modules") and room.modules:
                    for mod in room.modules.values():
                        if mod.__class__.__name__ == "NLC":
                            is_radiator = True
                            break
                
                if is_radiator:
                    # Config spécifique
                    conf = rooms_config.get(room_id, {})
                    entities.append(NetatmoRoomFilPilote(coordinator, home_id, room_id, data_handler, conf))
            
    async_add_entities(entities)


class NetatmoRoomFilPilote(CoordinatorEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON | 
        ClimateEntityFeature.TURN_OFF | 
        ClimateEntityFeature.PRESET_MODE |
        ClimateEntityFeature.TARGET_TEMPERATURE
    )
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, home_id, room_id, data_handler, config):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._handler = data_handler
        
        self._attr_unique_id = f"{home_id}-{room_id}"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name
        
        # --- CONFIGURATION HYBRIDE ---
        
        # 1. Tentative depuis la Config UI
        self._input_number_entity_id = config.get("input_number_entity")
        self._sensor_entity_id = config.get("sensor_entity")
        
        # 2. Fallback "Magic Link" (si non configuré)
        if not self._input_number_entity_id or not self._sensor_entity_id:
            slug_name = slugify(self._attr_name)
            
            if not self._input_number_entity_id:
                self._input_number_entity_id = f"input_number.consigne_{slug_name}"
                _LOGGER.debug(f"{self._attr_name}: Utilisation Input par défaut -> {self._input_number_entity_id}")
                
            if not self._sensor_entity_id:
                self._sensor_entity_id = f"sensor.temperature_{slug_name}_temperature"
                _LOGGER.debug(f"{self._attr_name}: Utilisation Sonde par défaut -> {self._sensor_entity_id}")

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_preset_mode = PRESET_NONE
        self._attr_target_temperature = 19
        self._attr_current_temperature = None 
        
        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model="Sortie de Câble Connectée (NLC)",
            suggested_area=self._attr_name,
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        entities_to_watch = []
        if self._sensor_entity_id: entities_to_watch.append(self._sensor_entity_id)
        if self._input_number_entity_id: entities_to_watch.append(self._input_number_entity_id)
        
        if entities_to_watch:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, entities_to_watch, self._on_external_update
                )
            )
            self._read_external_entities()

    @callback
    def _on_external_update(self, event):
        self._read_external_entities()
        self.async_write_ha_state()

    def _read_external_entities(self):
        if not self.hass: return

        if self._input_number_entity_id:
            state = self.hass.states.get(self._input_number_entity_id)
            if state and state.state not in ["unknown", "unavailable"]:
                try: self._attr_target_temperature = float(state.state)
                except ValueError: pass

        if self._sensor_entity_id:
            state = self.hass.states.get(self._sensor_entity_id)
            if state and state.state not in ["unknown", "unavailable"]:
                try: self._attr_current_temperature = float(state.state)
                except ValueError: pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        try:
            room = self.coordinator.data[self._home_id].rooms[self._room_id]
        except (KeyError, AttributeError):
            return
        
        self._read_external_entities()

        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        fp_val = getattr(room, "therm_setpoint_fp", None)

        if mode == NETATMO_MODE_OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_NONE
        elif mode == NETATMO_MODE_SCHEDULE or mode == "home":
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE
        elif mode == NETATMO_MODE_HG:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_AWAY
        elif mode == NETATMO_MODE_AWAY:
            self._attr_hvac_mode = HVACMode.COOL
            self._attr_preset_mode = PRESET_ECO
        elif mode == NETATMO_MODE_MANUAL:
            if fp_val == NETATMO_VAL_ECO_MAPPED:
                self._attr_hvac_mode = HVACMode.COOL
                self._attr_preset_mode = PRESET_ECO
            elif fp_val == NETATMO_VAL_FROST_GUARD:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_preset_mode = PRESET_AWAY
            else:
                self._attr_hvac_mode = HVACMode.HEAT
                self._attr_preset_mode = PRESET_COMFORT
        else:
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE

    async def async_set_temperature(self, **kwargs) -> None:
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is None or not self._input_number_entity_id: return

        self._attr_target_temperature = target_temp
        self.async_write_ha_state()

        try:
            await self.hass.services.async_call(
                "input_number", "set_value",
                {"entity_id": self._input_number_entity_id, "value": target_temp},
                blocking=False
            )
        except Exception as e:
            _LOGGER.error(f"Erreur update input_number: {e}")

    async def _async_push_pyatmo(self, mode_name, fp_val=None):
        try:
            home = self._handler.account.homes[self._home_id]
            room_payload = {"id": self._room_id, "therm_setpoint_mode": mode_name}
            
            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val: room_payload["therm_setpoint_fp"] = fp_val
                room_payload["therm_setpoint_temperature"] = 19
                room_payload["therm_setpoint_end_time"] = int(time.time() + DEFAULT_MANUAL_DURATION)

            _LOGGER.debug(f"Cmd: {room_payload}")
            await home.async_set_state({"rooms": [room_payload]})
            
        except Exception as e:
            _LOGGER.error(f"Erreur envoi: {e}")
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT and hvac_mode != HVACMode.COOL:
             self._attr_preset_mode = PRESET_NONE
        self.async_write_ha_state()

        if hvac_mode == HVACMode.OFF:
            self._attr_preset_mode = PRESET_AWAY
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_FROST_GUARD)
        elif hvac_mode == HVACMode.AUTO:
            self._attr_preset_mode = PRESET_NONE
            await self._async_push_pyatmo("home")
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_COMFORT)
        elif hvac_mode == HVACMode.COOL:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_ECO
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_ECO_MAPPED)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._attr_preset_mode = preset_mode
        if preset_mode == PRESET_ECO: self._attr_hvac_mode = HVACMode.COOL
        elif preset_mode == PRESET_AWAY: self._attr_hvac_mode = HVACMode.OFF
        elif preset_mode == PRESET_NONE: self._attr_hvac_mode = HVACMode.AUTO
        else: self._attr_hvac_mode = HVACMode.HEAT
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