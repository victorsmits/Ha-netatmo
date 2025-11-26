"""Light platform using Pyatmo."""
from __future__ import annotations

import logging
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, SUPPORTED_LIGHT_TYPES, DIMMER_TYPES
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    for home_id, home in coordinator.homes.items():
        for module_id, module in home.modules.items():
            if module.device_type in SUPPORTED_LIGHT_TYPES:
                entities.append(NetatmoLight(coordinator, home_id, module_id))
    
    async_add_entities(entities)

class NetatmoLight(CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, home_id, module_id):
        super().__init__(coordinator)
        self._home_id = home_id
        self._module_id = module_id
        self._attr_unique_id = f"netatmo_light_{module_id}"

    @property
    def _module(self):
        return self.coordinator.homes[self._home_id].modules[self._module_id]

    @property
    def name(self) -> str:
        return self._module.name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=self.name,
            manufacturer="Legrand/Netatmo",
            model=self._module.device_type,
            via_device=(DOMAIN, self._home_id),
        )

    @property
    def is_on(self) -> bool:
        # Pyatmo expose souvent 'on' via une propriété ou un get
        # Sur les versions récentes c'est souvent un attribut direct si dynamique
        return getattr(self._module, "on", False)

    @property
    def brightness(self) -> int | None:
        # Pyatmo 0-100
        bri = getattr(self._module, "brightness", None)
        if bri is not None: return int(bri * 255 / 100)
        return None

    @property
    def supported_color_modes(self) -> set:
        if self._module.device_type in DIMMER_TYPES:
            return {ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> str:
        return ColorMode.BRIGHTNESS if self._module.device_type in DIMMER_TYPES else ColorMode.ONOFF

    async def async_turn_on(self, **kwargs):
        bri = kwargs.get("brightness")
        netatmo_bri = int(bri * 100 / 255) if bri else None
        if netatmo_bri and netatmo_bri < 1: netatmo_bri = 1
        
        await self.coordinator.async_set_light_state(
            self._home_id, self._module_id, on=True, brightness=netatmo_bri
        )

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_light_state(self._home_id, self._module_id, on=False)