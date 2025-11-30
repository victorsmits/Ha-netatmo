"""Climate platform for Netatmo Modular integration."""
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
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    NETATMO_PRESET_SCHEDULE,
    NETATMO_TO_PRESET_MAP,
    PRESET_MODES,
    PRESET_TO_NETATMO_MAP,
    TEMP_STEP,
)
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo climate entities."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    entities = []
    # Parcourir les maisons et pièces via Pyatmo
    for home in coordinator.homes.values():
        for room in home.rooms.values():
            # Vérifier si la pièce a un thermostat/vanne
            if room.modules:
                entities.append(NetatmoClimate(coordinator, room.entity_id, home.entity_id))

    async_add_entities(entities)


class NetatmoClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a Netatmo climate device."""

    _attr_has_entity_name = True
    _attr_translation_key = "netatmo_thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESET_MODES

    def __init__(self, coordinator: NetatmoDataUpdateCoordinator, room_id: str, home_id: str) -> None:
        super().__init__(coordinator)
        self._room_id = room_id
        self._home_id = home_id
        self._attr_unique_id = f"netatmo_modular_climate_{room_id}"

    @property
    def _room(self):
        return self.coordinator.get_room(self._room_id)

    @property
    def device_info(self) -> DeviceInfo:
        room = self._room
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=room.name if room else "Unknown Room",
            manufacturer="Netatmo",
            via_device=(DOMAIN, self._home_id),
        )

    @property
    def current_temperature(self) -> float | None:
        return self._room.therm_measured_temperature

    @property
    def target_temperature(self) -> float | None:
        return self._room.therm_setpoint_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._room.therm_setpoint_mode
        if mode == NETATMO_PRESET_SCHEDULE:
            return HVACMode.AUTO
        if mode == "manual":
            return HVACMode.HEAT
        if mode in ["off", "away", "hg", "frost_guard"]:
            return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def preset_mode(self) -> str | None:
        mode = self._room.therm_setpoint_mode
        if mode == "manual":
            return None 
        return NETATMO_TO_PRESET_MAP.get(mode)

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        power = getattr(self._room, "heating_power_request", 0)
        if power and power > 0:
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get("temperature")
        if temp is None:
            return
        
        # Appel API
        await self._room.async_therm_set(mode="manual", temp=temp)
        
        # --- Optimistic Update ---
        # On force les valeurs locales pour que l'UI change tout de suite
        self._room.therm_setpoint_mode = "manual"
        self._room.therm_setpoint_temperature = temp
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        target_mode = None
        
        if hvac_mode == HVACMode.OFF:
            target_mode = "hg" # Frost guard
        elif hvac_mode == HVACMode.AUTO:
            target_mode = "home" # Schedule
        elif hvac_mode == HVACMode.HEAT:
            # Passage en manuel, on garde la température actuelle comme cible
            target_mode = "manual"
            current_temp = self.current_temperature or 20
            # Appel spécial avec température pour le mode manual
            await self._room.async_therm_set(mode="manual", temp=current_temp)
            
            # Optimistic Update spécifique
            self._room.therm_setpoint_mode = "manual"
            self._room.therm_setpoint_temperature = current_temp
            self.async_write_ha_state()
            return

        # Appel API pour les modes non-manuel (Auto/Off)
        if target_mode:
            await self._room.async_therm_set(mode=target_mode)
            
            # --- Optimistic Update ---
            # Si on passe en 'home', l'API renvoie souvent 'schedule' dans le statut
            if target_mode == "home":
                self._room.therm_setpoint_mode = "schedule"
            else:
                self._room.therm_setpoint_mode = target_mode
                
            self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        netatmo_mode = PRESET_TO_NETATMO_MAP.get(preset_mode)
        
        if netatmo_mode:
            # Appel API
            await self._room.async_therm_set(mode=netatmo_mode)
            
            # --- Optimistic Update ---
            self._room.therm_setpoint_mode = netatmo_mode
            self.async_write_ha_state()