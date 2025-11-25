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
    MAX_TEMP,
    MIN_TEMP,
    PRESET_MODES,
    TEMP_STEP,
)
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Mapping pour la lecture : Valeur API Netatmo -> Preset Home Assistant
NETATMO_TO_PRESET = {
    "manual": None,         # Sera déterminé par therm_setpoint_fp
    "max": "comfort",
    "frost_guard": "frost_guard",
    "hg": "frost_guard",
    "off": "away",
    "schedule": "schedule",
    "home": "schedule",
    "away": "away",
    "comfort": "comfort",
    "eco": "away",          # Eco est mappé sur Away (Absent)
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo climate entities from a config entry."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[NetatmoClimate] = []

    for room_id, room in coordinator.rooms.items():
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
    _attr_translation_key = "netatmo_thermostat"
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
        """Return current HVAC mode based on FP."""
        setpoint_mode = self._room.get("therm_setpoint_mode", "schedule")
        home_mode = self._home.get("therm_mode", "schedule")
        fp_mode = self._room.get("therm_setpoint_fp")

        # 1. Gestion du mode AUTO (Planning)
        if setpoint_mode in ("schedule", "home") or home_mode in ("schedule", "home"):
            return HVACMode.AUTO

        # 2. Gestion du mode MANUEL avec Fil Pilote
        if setpoint_mode == "manual":
            # Correction : on cherche "frost_guard" ou "hg" -> OFF
            if fp_mode in ("frost_guard", "hg"):
                return HVACMode.OFF
            # Sinon (Comfort, Away) -> HEAT
            return HVACMode.HEAT

        # 3. Gestion des modes explicites OFF/Away/HG
        if setpoint_mode in ("off", "away", "frost_guard", "hg"):
            return HVACMode.OFF

        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        # LA CORRECTION EST ICI :
        heating_power = self._room.get("heating_power_request")
        if heating_power is not None and heating_power > 0:
            return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode based on FP."""
        setpoint_mode = self._room.get("therm_setpoint_mode", "schedule")
        fp_mode = self._room.get("therm_setpoint_fp")

        if setpoint_mode == "schedule":
            return "schedule"

        if setpoint_mode == "manual":
            # Lecture du Fil Pilote
            if fp_mode == "comfort":
                return "comfort"
            elif fp_mode == "away": 
                return "away"
            # Correction "frost_guard"
            elif fp_mode in ("frost_guard", "hg"):
                return "frost_guard"
            # Si on reçoit "eco", on retourne "away" comme demandé
            elif fp_mode == "eco":
                return "away"
        
        if setpoint_mode in ("frost_guard", "hg"):
            return "frost_guard"
            
        if setpoint_mode == "away":
            return "away"

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
            "fil_pilote": self._room.get("therm_setpoint_fp"),
        }

        for module_id in self._room.get("module_ids", []):
            module = self.coordinator.get_module(module_id)
            if module and module.get("boiler_status") is not None:
                attrs[ATTR_BOILER_STATUS] = module.get("boiler_status")
                break

        return {k: v for k, v in attrs.items() if v is not None}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature (Ignored for FP radiators)."""
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        _LOGGER.debug("Setting preset mode for room %s to %s", self._room_id, preset_mode)

        if preset_mode == "schedule":
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="home",
            )
        elif preset_mode == "away":
            # Away = Away
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="manual",
                fp="away"
            )
        elif preset_mode == "frost_guard":
            # Frost Guard = "frost_guard"
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="manual",
                fp="frost_guard"
            )
        elif preset_mode == "comfort":
            await self.coordinator.async_set_room_mode(
                room_id=self._room_id,
                mode="manual",
                fp="comfort", 
            )
        
        # Force refresh
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            # Éteindre = Hors-Gel ("frost_guard")
            await self.async_set_preset_mode("frost_guard")
        elif hvac_mode == HVACMode.AUTO:
            await self.async_set_preset_mode("schedule")
        elif hvac_mode == HVACMode.HEAT:
            # Allumer = Confort
            await self.async_set_preset_mode("comfort")

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