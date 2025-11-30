"""Climate platform for Netatmo Modular integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
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
    NETATMO_TO_PRESET_MAP,
    PRESET_MODES,
    PRESET_TO_NETATMO_MAP,
    PRESET_MANUAL,
    PRESET_FROST_GUARD,
    PRESET_SCHEDULE,
    PRESET_AWAY,
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
    for home in coordinator.homes.values():
        for room in home.rooms.values():
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

    # HYBRIDE : Auto (Planning), Heat (Manuel), Off (Hors-gel)
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
        """Retourne le mode principal (Auto/Heat/Off)."""
        mode = self._room.therm_setpoint_mode

        # OFF / HORS-GEL
        if mode in ["off", "hg", "frost_guard"]:
            return HVACMode.OFF

        # SCHEDULE / HOME -> AUTO
        if mode in ["schedule", "home"]:
            return HVACMode.AUTO

        # MANUAL / AWAY -> HEAT (car c'est une dérogation active)
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        """Retourne le preset actif."""
        mode = self._room.therm_setpoint_mode
        return NETATMO_TO_PRESET_MAP.get(mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Changer la température force le mode Manuel (Heat)."""
        temp = kwargs.get("temperature")
        if temp is None:
            return

        await self._room.async_therm_set(mode="manual", temp=temp)

        # Optimistic
        self._room.therm_setpoint_mode = "manual"
        self._room.therm_setpoint_temperature = temp
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Changer le mode principal (Boutons ronds)."""

        if hvac_mode == HVACMode.OFF:
            # OFF -> Preset Hors-gel
            await self.async_set_preset_mode(PRESET_FROST_GUARD)

        elif hvac_mode == HVACMode.AUTO:
            # AUTO -> Preset Planning
            await self.async_set_preset_mode(PRESET_SCHEDULE)

        elif hvac_mode == HVACMode.HEAT:
            # HEAT -> Preset Manuel (avec temp actuelle)
            await self.async_set_preset_mode(PRESET_MANUAL)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Choisir dans la liste des presets."""
        netatmo_mode = PRESET_TO_NETATMO_MAP.get(preset_mode)

        if netatmo_mode:
            if preset_mode == PRESET_MANUAL:
                current = self.current_temperature or 20
                await self._room.async_therm_set(mode="manual", temp=current)
            else:
                await self._room.async_therm_set(mode=netatmo_mode)

            # Optimistic Update
            # On mappe 'home' vers 'schedule' pour l'affichage local HA
            if netatmo_mode == "home":
                self._room.therm_setpoint_mode = "schedule"
            else:
                self._room.therm_setpoint_mode = netatmo_mode

            self.async_write_ha_state()