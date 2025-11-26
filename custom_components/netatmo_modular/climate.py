"""Climate platform using Pyatmo."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_SLEEP,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_HOME_ID,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    NETATMO_TO_PRESET_MAP,
    PRESET_MODES,
    PRESET_TO_NETATMO_MAP,
    TEMP_STEP,
)
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    # On parcourt les maisons Pyatmo
    for home_id, home in coordinator.homes.items():
        for room_id, room in home.rooms.items():
            # On vérifie si la pièce a des modules de chauffage
            # Pyatmo: room.modules est une liste d'IDs
            # On peut aussi vérifier climate_type
            if any(mod_id in home.modules for mod_id in room.modules):
                 entities.append(NetatmoClimate(coordinator, home_id, room_id))

    async_add_entities(entities)

class NetatmoClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "netatmo_thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESET_MODES
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    def __init__(self, coordinator, home_id, room_id):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._attr_unique_id = f"netatmo_climate_{room_id}"

    @property
    def _home(self):
        return self.coordinator.homes[self._home_id]

    @property
    def _room(self):
        return self._home.rooms[self._room_id]

    @property
    def name(self) -> str:
        return self._room.name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=f"{self._home.name} - {self._room.name}",
            manufacturer="Netatmo",
            model="Thermostat",
            via_device=(DOMAIN, self._home_id),
        )

    @property
    def current_temperature(self):
        return self._room.therm_measured_temperature

    @property
    def target_temperature(self):
        return self._room.therm_setpoint_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._room.therm_setpoint_mode
        fp = self._room.therm_setpoint_fp
        
        if mode in ("schedule", "home"): return HVACMode.AUTO
        if mode == "manual":
            if fp in ("frost_guard", "hg"): return HVACMode.OFF
            return HVACMode.HEAT
        if mode in ("away", "frost_guard", "hg", "off"): return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF: return HVACAction.OFF
        # Pyatmo retourne 0 ou int
        if (self._room.heating_power_request or 0) > 0: return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        mode = self._room.therm_setpoint_mode
        fp = self._room.therm_setpoint_fp
        
        if mode == "schedule": return PRESET_HOME
        if mode == "manual":
            return NETATMO_TO_PRESET_MAP.get(fp, PRESET_COMFORT)
        return NETATMO_TO_PRESET_MAP.get(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        netatmo_cmd = PRESET_TO_NETATMO_MAP.get(preset_mode)
        if not netatmo_cmd: return
        
        if preset_mode == PRESET_HOME:
            await self.coordinator.async_set_room_mode(self._home_id, self._room_id, "schedule")
        else:
            await self.coordinator.async_set_room_mode(self._home_id, self._room_id, "manual", fp=netatmo_cmd)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF: await self.async_set_preset_mode(PRESET_SLEEP)
        elif hvac_mode == HVACMode.AUTO: await self.async_set_preset_mode(PRESET_HOME)
        elif hvac_mode == HVACMode.HEAT: await self.async_set_preset_mode(PRESET_COMFORT)

    async def async_turn_on(self): await self.async_set_hvac_mode(HVACMode.AUTO)
    async def async_turn_off(self): await self.async_set_hvac_mode(HVACMode.OFF)
    async def async_set_temperature(self, **kwargs): pass