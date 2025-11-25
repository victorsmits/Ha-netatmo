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
    PRESET_ECO,
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
    ATTR_ANTICIPATING,
    ATTR_BOILER_STATUS,
    ATTR_FIL_PILOTE,
    ATTR_HEATING_POWER_REQUEST,
    ATTR_HOME_ID,
    ATTR_OPEN_WINDOW,
    ATTR_ROOM_ID,
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
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Optimisation : List comprehension plus rapide
    entities = [
        NetatmoClimate(coordinator, room_id)
        for room_id, room in coordinator.rooms.items()
        if room.get("module_ids")
    ]

    async_add_entities(entities)


class NetatmoClimate(CoordinatorEntity[NetatmoDataUpdateCoordinator], ClimateEntity):
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

    def __init__(self, coordinator: NetatmoDataUpdateCoordinator, room_id: str) -> None:
        super().__init__(coordinator)
        self._room_id = room_id
        self._attr_unique_id = f"netatmo_modular_climate_{room_id}"

    @property
    def _room(self) -> dict[str, Any]:
        """Get room data safely."""
        return self.coordinator.get_room(self._room_id) or {}

    @property
    def name(self) -> str:
        return self._room.get("name", f"Room {self._room_id}")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=f"{self._room.get('home_name', 'Netatmo')} - {self.name}",
            manufacturer="Netatmo",
            model="Smart Thermostat Room",
            via_device=(DOMAIN, self._room.get("home_id", "")),
        )

    @property
    def current_temperature(self) -> float | None:
        return self._room.get("therm_measured_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self._room.get("therm_setpoint_temperature")

    @property
    def hvac_mode(self) -> HVACMode:
        setpoint_mode = self._room.get("therm_setpoint_mode")
        fp_mode = self._room.get("therm_setpoint_fp")

        # AUTO : Si mode est schedule ou home
        if setpoint_mode in (NETATMO_PRESET_SCHEDULE, "home"):
            return HVACMode.AUTO

        # OFF : Si mode explicitement éteint ou hors-gel
        if setpoint_mode in ("off", "away") or fp_mode in ("frost_guard", "hg"):
            return HVACMode.OFF

        # HEAT : Si manuel et pas hors-gel
        if setpoint_mode == "manual":
            return HVACMode.HEAT

        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        heating_power = self._room.get("heating_power_request")
        if heating_power is not None and heating_power > 0:
            return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        setpoint_mode = self._room.get("therm_setpoint_mode")
        fp_mode = self._room.get("therm_setpoint_fp")

        # Cas spéciaux pour le mapping
        if setpoint_mode == NETATMO_PRESET_SCHEDULE:
            return PRESET_HOME

        if setpoint_mode == "manual":
            # On utilise le mapping défini dans const.py
            return NETATMO_TO_PRESET_MAP.get(fp_mode)
        
        # Fallback
        return NETATMO_TO_PRESET_MAP.get(setpoint_mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {
            ATTR_HOME_ID: self._room.get("home_id"),
            ATTR_ROOM_ID: self._room_id,
            ATTR_HEATING_POWER_REQUEST: self._room.get("heating_power_request"),
            ATTR_ANTICIPATING: self._room.get("anticipating"),
            ATTR_OPEN_WINDOW: self._room.get("open_window"),
            ATTR_FIL_PILOTE: self._room.get("therm_setpoint_fp"),
        }
        return {k: v for k, v in attrs.items() if v is not None}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature (Ignored for FP radiators)."""
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode efficiently."""
        netatmo_fp = PRESET_TO_NETATMO_MAP.get(preset_mode)
        
        if preset_mode == PRESET_HOME:
            await self.coordinator.async_set_room_mode(self._room_id, mode=NETATMO_PRESET_SCHEDULE)
        elif netatmo_fp:
            await self.coordinator.async_set_room_mode(self._room_id, mode="manual", fp=netatmo_fp)
        
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        target_preset = None
        
        if hvac_mode == HVACMode.OFF:
            target_preset = PRESET_SLEEP # Hors-gel
        elif hvac_mode == HVACMode.AUTO:
            target_preset = PRESET_HOME  # Planning
        elif hvac_mode == HVACMode.HEAT:
            target_preset = PRESET_COMFORT

        if target_preset:
            await self.async_set_preset_mode(target_preset)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()