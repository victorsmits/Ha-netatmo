"""Light platform for Netatmo Modular integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SUPPORTED_LIGHT_TYPES,
    DEVICE_TYPE_DIMMER,
    DEVICE_TYPE_DIMMER2,
)
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo light entities."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = [
        NetatmoLight(coordinator, module_id)
        for module_id, module in coordinator.modules.items()
        if module.get("type") in SUPPORTED_LIGHT_TYPES
    ]

    async_add_entities(entities)


class NetatmoLight(CoordinatorEntity[NetatmoDataUpdateCoordinator], LightEntity):
    """Representation of a Netatmo Light."""

    _attr_has_entity_name = True
    _attr_name = None  # Uses device name

    def __init__(self, coordinator: NetatmoDataUpdateCoordinator, module_id: str) -> None:
        super().__init__(coordinator)
        self._module_id = module_id
        self._attr_unique_id = f"netatmo_light_{module_id}"

    @property
    def _module(self) -> dict[str, Any]:
        return self.coordinator.get_module(self._module_id) or {}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=self._module.get("name", "Unknown Light"),
            manufacturer="Netatmo/Legrand",
            model=self._module.get("type"),
            via_device=(DOMAIN, self._module.get("home_id", "")),
        )

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._module.get("on", False)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light (0-255)."""
        # Netatmo renvoie 0-100, HA veut 0-255
        netatmo_bri = self._module.get("brightness")
        if netatmo_bri is not None:
            return int(netatmo_bri * 255 / 100)
        return None

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        # Détection intelligente : Type Variateur OU Donnée luminosité présente
        is_dimmer_type = self._module.get("type") in [DEVICE_TYPE_DIMMER, DEVICE_TYPE_DIMMER2]
        has_brightness_data = self._module.get("brightness") is not None

        if is_dimmer_type or has_brightness_data:
            return {ColorMode.BRIGHTNESS}
        
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> str | None:
        """Return the current color mode."""
        if ColorMode.BRIGHTNESS in self.supported_color_modes:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get("brightness")
        
        netatmo_bri = None
        if brightness is not None:
            # HA (0-255) -> Netatmo (0-100)
            netatmo_bri = int(brightness * 100 / 255)
            # Netatmo ne descend pas en dessous de 1% si on demande d'allumer
            if netatmo_bri < 1: netatmo_bri = 1

        await self.coordinator.async_set_light_state(
            self._module_id, 
            on=True, 
            brightness=netatmo_bri
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.coordinator.async_set_light_state(self._module_id, on=False)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()