from __future__ import annotations

from typing import Any
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, SUPPORTED_LIGHT_TYPES

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(NetatmoLight(coordinator, module.entity_id, home.entity_id) for home in coordinator.homes.values() for module in home.modules.values() if getattr(module, "device_type", None) in SUPPORTED_LIGHT_TYPES)

class NetatmoLight(CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, module_id, home_id):
        super().__init__(coordinator)
        self._module_id = module_id
        self._home_id = home_id
        self._attr_unique_id = f"netatmo_light_{module_id}"

    @property
    def _module(self):
        return self.coordinator.get_module(self._module_id)

    @property
    def device_info(self):
        mod = self._module
        return {"identifiers": {(DOMAIN, self._module_id)}, "name": mod.name, "manufacturer": "Legrand/Netatmo", "model": getattr(mod, "device_type", "Unknown"), "via_device": (DOMAIN, self._home_id)}

    @property
    def is_on(self):
        return getattr(self._module, "on", False)

    @property
    def brightness(self):
        val = getattr(self._module, "brightness", None)
        return int(val * 255 / 100) if val is not None else None

    @property
    def supported_color_modes(self):
        return {ColorMode.BRIGHTNESS} if self.brightness is not None else {ColorMode.ONOFF}

    @property
    def color_mode(self):
        return ColorMode.BRIGHTNESS if ColorMode.BRIGHTNESS in self.supported_color_modes else ColorMode.ONOFF

    async def async_turn_on(self, **kwargs):
        bri = kwargs.get("brightness")
        if bri is not None:
            await self._module.async_set_state(on=True, brightness=int(bri * 100 / 255))
            self._module.brightness = int(bri * 100 / 255)
        else:
            await self._module.async_set_state(on=True)
        self._module.on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._module.async_set_state(on=False)
        self._module.on = False
        self.async_write_ha_state()