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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ANTICIPATING,
    ATTR_BOILER_STATUS,
    ATTR_HEATING_POWER_REQUEST,
    ATTR_HOME_ID,
    ATTR_OPEN_WINDOW,
    ATTR_ROOM_ID,
    DOMAIN,
    HA_TO_NETATMO_HVAC_MODE,
    MAX_TEMP,
    MIN_TEMP,
    NETATMO_TO_HA_HVAC_MODE,
    PRESET_MODES,
    TEMP_STEP,
)
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Mapping Netatmo setpoint modes to HA preset modes
NETATMO_TO_PRESET = {
    "manual": None,  # Manual mode has no preset
    "max": "comfort",
    "hg": "frost_guard",
    "off": "away",
    "schedule": "schedule",
    "away": "away",
    "comfort": "comfort",
    "eco": "eco",
    "frost_guard": "frost_guard",
}

PRESET_TO_NETATMO = {
    "comfort": "manual",  # Will set high temp
    "eco": "manual",  # Will set low temp
    "frost_guard": "hg",
    "away": "away",
    "schedule": "schedule",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo climate entities from a config entry."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[NetatmoClimate] = []

    # Create a climate entity for each room that has heating capability
    for room_id, room in coordinator.rooms.items():
        # Check if room has any modules (heating devices)
        if room.get("module_ids"):
            _LOGGER.debug(
                "Creating climate entity for room: %s (%s)",
                room.get("name"),
                room_id,
            )
            entities.append(
                NetatmoClimate(
                    coordinator=coordinator,
                    room_id=room_id,
                )
            )

    _LOGGER.info("Setting up %d Netatmo climate entities", len(entities))
    async_add_entities(entities)


class NetatmoClimate(CoordinatorEntity[NetatmoDataUpdateCoordinator], ClimateEntity):
    """Representation of a Netatmo climate device (room thermostat)."""

    _attr_has_entity_name = True
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

    _attr_hvac_modes = [
        HVACMode.AUTO,
        HVACMode.HEAT,
        HVACMode.OFF,
    ]

    _attr_preset_modes = PRESET_MODES

    def __init__(
        self,
        coordinator: NetatmoDataUpdateCoordinator,
        room_id: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._attr_unique_id = f"netatmo_modular_climate_{room_id}"

    @property
    def _room(self) -> dict[str, Any]:
        """Get current room data."""
        return self.coordinator.get_room(self._room_id) or {}

    @property
    def _home(self) -> dict[str, Any]:
        """Get home data for this room."""
        return self.coordinator.get_home_for_room(self._room_id) or {}

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._room.get("name", f"Room {self._room_id}")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        home_name = self._room.get("home_name", "Netatmo Home")
        room_name = self._room.get("name", "Unknown Room")

        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=f"{home_name} - {room_name}",
            manufacturer="Netatmo",
            model="Smart Thermostat Room",
            via_device=(DOMAIN, self._room.get("home_id", "")),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._room_id in self.coordinator.rooms

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._room.get("therm_measured_temperature")

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._room.get("therm_setpoint_temperature")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        setpoint_mode = self._room.get("therm_setpoint_mode", "schedule")
        home_mode = self._home.get("therm_mode", "schedule")

        # Map Netatmo mode to HA mode
        if setpoint_mode == "off" or home_mode == "off":
            return HVACMode.OFF
        elif setpoint_mode == "schedule" or home_mode == "schedule":
            return HVACMode.AUTO
        elif setpoint_mode in ("manual", "max", "comfort"):
            return HVACMode.HEAT
        elif setpoint_mode in ("away", "hg"):
            return HVACMode.OFF

        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        heating_power = self._room.get("heating_power_request", 0)

        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        if heating_power and heating_power > 0:
            return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        setpoint_mode = self._room.get("therm_setpoint_mode", "schedule")
        return NETATMO_TO_PRESET.get(setpoint_mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            ATTR_HOME_ID: self._room.get("home_id"),
            ATTR_ROOM_ID: self._room_id,
            ATTR_HEATING_POWER_REQUEST: self._room.get("heating_power_request"),
            ATTR_ANTICIPATING: self._room.get("anticipating"),
            ATTR_OPEN_WINDOW: self._room.get("open_window"),
        }

        # Add boiler status if available
        for module_id in self._room.get("module_ids", []):
            module = self.coordinator.get_module(module_id)
            if module and module.get("boiler_status") is not None:
                attrs[ATTR_BOILER_STATUS] = module.get("boiler_status")
                break

        return {k: v for k, v in attrs.items() if v is not None}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        _LOGGER.debug(
            "Setting temperature for room %s to %s",
            self._room_id,
            temperature,
        )

        await self.coordinator.async_set_room_mode(
            room_id=self._room_id,
            mode="manual",
            temp=temperature,
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        _LOGGER.debug("Setting HVAC mode for room %s to %s", self._room_id, hvac_mode)

        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="off",
            )
        elif hvac_mode == HVACMode.AUTO:
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="home",  # Return to schedule
            )
        elif hvac_mode == HVACMode.HEAT:
            # Set to manual with current or default temperature
            current_target = self.target_temperature or 20
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="manual",
                temp=current_target,
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        _LOGGER.debug("Setting preset mode for room %s to %s", self._room_id, preset_mode)

        if preset_mode == "schedule":
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="home",
            )
        elif preset_mode == "away":
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="away",
            )
        elif preset_mode == "frost_guard":
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="hg",
            )
        elif preset_mode == "comfort":
            # Comfort = max temperature (or high temp)
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="manual",
                temp=self.max_temp - 2,  # 28°C as comfort
            )
        elif preset_mode == "eco":
            # Eco = lower temperature
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="manual",
                temp=self.min_temp + 3,  # 10°C as eco
            )

    async def async_turn_on(self) -> None:
        """Turn on the climate device."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        """Turn off the climate device."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
