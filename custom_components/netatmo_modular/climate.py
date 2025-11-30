from __future__ import annotations

from typing import Any
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, MAX_TEMP, MIN_TEMP, NETATMO_TO_PRESET_MAP, PRESET_MODES, PRESET_TO_NETATMO_MAP, PRESET_MANUAL, TEMP_STEP

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(NetatmoClimate(coordinator, room.entity_id, home.entity_id) for home in coordinator.homes.values() for room in home.rooms.values() if room.modules)

class NetatmoClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "netatmo_thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESET_MODES

    def __init__(self, coordinator, room_id, home_id):
        super().__init__(coordinator)
        self._room_id = room_id
        self._home_id = home_id
        self._attr_unique_id = f"netatmo_modular_climate_{room_id}"

    @property
    def _room(self):
        return self.coordinator.get_room(self._room_id)

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._room_id)}, "name": self._room.name, "manufacturer": "Netatmo", "via_device": (DOMAIN, self._home_id)}

    @property
    def current_temperature(self):
        return self._room.therm_measured_temperature

    @property
    def target_temperature(self):
        return self._room.therm_setpoint_temperature

    @property
    def hvac_mode(self):
        mode = self._room.therm_setpoint_mode
        if mode in ["off", "hg", "frost_guard"]: return HVACMode.OFF
        return HVACMode.AUTO if mode in ["schedule", "home"] else HVACMode.HEAT

    @property
    def preset_mode(self):
        return NETATMO_TO_PRESET_MAP.get(self._room.therm_setpoint_mode)

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get("temperature")
        if temp:
            await self._room.async_therm_set(mode="manual", temp=temp)
            self._room.therm_setpoint_mode = "manual"
            self._room.therm_setpoint_temperature = temp
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self.async_set_preset_mode("frost_guard")
        elif hvac_mode == HVACMode.AUTO:
            await self.async_set_preset_mode("schedule")
        elif hvac_mode == HVACMode.HEAT:
            await self.async_set_preset_mode("manual")

    async def async_set_preset_mode(self, preset_mode):
        netatmo_mode = PRESET_TO_NETATMO_MAP.get(preset_mode)
        if netatmo_mode:
            if preset_mode == PRESET_MANUAL:
                await self._room.async_therm_set(mode="manual", temp=self.current_temperature or 20)
            else:
                await self._room.async_therm_set(mode=netatmo_mode)
            self._room.therm_setpoint_mode = "schedule" if netatmo_mode == "home" else netatmo_mode
            self.async_write_ha_state()