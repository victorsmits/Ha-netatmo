"""Support des Lumières Legrand/Netatmo (Fix Bridge ID)."""
import logging
from typing import Any
from datetime import timedelta

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    ATTR_BRIGHTNESS
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Types reconnus
LIGHT_TYPES = ["NLF", "NLFN", "NLFE", "NLV", "NLL", "NLUP", "NLO", "Dimmer", "Switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data_context = hass.data[DOMAIN][entry.entry_id]
    coordinator = data_context["coordinator"]
    data_handler = data_context["api"]

    entities = []
    
    for home_id, home in coordinator.data.items():
        if not home.modules: continue
        
        for module_id, module in home.modules.items():
            mod_class = module.__class__.__name__
            
            if mod_class in LIGHT_TYPES:
                entities.append(NetatmoLight(coordinator, home_id, module_id, data_handler))
            
    async_add_entities(entities)


class NetatmoLight(CoordinatorEntity, LightEntity):
    """Représentation d'une lumière Legrand."""

    def __init__(self, coordinator, home_id, module_id, data_handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._module_id = module_id
        self._handler = data_handler
        
        self._attr_unique_id = f"{module_id}-light"
        
        module = self._get_module()
        if module and hasattr(module, "name"):
            self._attr_name = module.name
        else:
            self._attr_name = f"Lumière {module_id}"
        
        # Configuration
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF
        
        if module and hasattr(module, "brightness"):
             self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
             self._attr_color_mode = ColorMode.BRIGHTNESS
        
        self._is_on = False
        self._brightness = 255
        
        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        module = self._get_module()
        model_name = module.__class__.__name__ if module else "Legrand Light"
        
        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model=model_name,
            suggested_area=self._attr_name,
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int | None:
        return self._brightness

    def _get_module(self):
        try:
            return self.coordinator.data[self._home_id].modules[self._module_id]
        except (KeyError, AttributeError):
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        module = self._get_module()
        if not module: return

        # Lecture On/Off
        self._is_on = getattr(module, "on", False)
        
        # Lecture Brightness
        if self._attr_color_mode == ColorMode.BRIGHTNESS:
            netatmo_bright = getattr(module, "brightness", None)
            if netatmo_bright is not None:
                self._brightness = int(netatmo_bright * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allumer."""
        brightness_ha = kwargs.get(ATTR_BRIGHTNESS)
        brightness_netatmo = None
        
        if self._attr_color_mode == ColorMode.BRIGHTNESS:
            if brightness_ha is None:
                self._brightness = 255
            else:
                brightness_netatmo = int(brightness_ha * 100 / 255)
                if brightness_netatmo < 1: brightness_netatmo = 1
                self._brightness = brightness_ha

        # Optimistic
        self._is_on = True
        self.async_write_ha_state()

        await self._async_push_command(True, brightness_netatmo)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Eteindre."""
        self._is_on = False
        self.async_write_ha_state()
        await self._async_push_command(False, None)

    async def _async_push_command(self, on_state, brightness_val):
        """Envoi via setstate avec Bridge ID."""
        try:
            home = self._handler.account.homes[self._home_id]
            
            # Récupération de l'objet module pour trouver son bridge
            module = self._get_module()
            bridge_id = getattr(module, "bridge", None)

            module_data = {
                "id": self._module_id,
                "on": on_state
            }
            
            # CORRECTION CRITIQUE : Ajout du Bridge ID
            # L'API Legrand en a besoin pour router la commande Zigbee
            if bridge_id:
                module_data["bridge"] = bridge_id
            
            if on_state and brightness_val is not None:
                module_data["brightness"] = brightness_val

            _LOGGER.debug(f"Cmd Light (Bridge={bridge_id}): {module_data}")
            
            # Utilisation du wrapper officiel
            await home.async_set_state({"modules": [module_data]})
            
        except Exception as e:
            _LOGGER.error(f"Erreur Light: {e}")
            await self.coordinator.async_request_refresh()