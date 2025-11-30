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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SUPPORTED_LIGHT_TYPES, DEVICE_TYPE_DIMMER, DEVICE_TYPE_DIMMER2
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo light entities."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    entities = []
    for home in coordinator.homes.values():
        for module in home.modules.values():
            if getattr(module, "device_type", None) in SUPPORTED_LIGHT_TYPES:
                entities.append(NetatmoLight(coordinator, module.entity_id, home.entity_id))

    async_add_entities(entities)


class NetatmoLight(CoordinatorEntity, LightEntity):
    """Representation of a Netatmo Light."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NetatmoDataUpdateCoordinator, module_id: str, home_id: str) -> None:
        super().__init__(coordinator)
        self._module_id = module_id
        self._home_id = home_id
        self._attr_unique_id = f"netatmo_light_{module_id}"

    @property
    def _module(self):
        return self.coordinator.get_module(self._module_id)

    @property
    def device_info(self) -> DeviceInfo:
        module = self._module
        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=module.name if module else "Unknown Light",
            manufacturer="Legrand/Netatmo",
            model=getattr(module, "device_type", "Unknown"),
            via_device=(DOMAIN, self._home_id),
        )

    @property
    def is_on(self) -> bool:
        # Pyatmo retourne un booléen pour 'on'
        return getattr(self._module, "on", False)

    @property
    def brightness(self) -> int | None:
        # Pyatmo : 0-100 ou None
        val = getattr(self._module, "brightness", None)
        if val is not None:
            return int(val * 255 / 100)
        return None

    @property
    def supported_color_modes(self) -> set[str] | None:
        dtype = getattr(self._module, "device_type", "")
        # Si c'est un dimmer connu ou qu'on a une info de luminosité
        if dtype in [DEVICE_TYPE_DIMMER, DEVICE_TYPE_DIMMER2] or self.brightness is not None:
            return {ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> str | None:
        if ColorMode.BRIGHTNESS in self.supported_color_modes:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = kwargs.get("brightness")
        
        # Si brightness demandé, on convertit 0-255 -> 0-100
        if brightness is not None:
            b_pct = int(brightness * 100 / 255)
            # Pyatmo 'set_state' gère 'brightness'
            await self._module.async_set_state(on=True, brightness=b_pct)
        else:
            await self._module.async_set_state(on=True)
            
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._module.async_set_state(on=False)
        self.async_write_ha_state()