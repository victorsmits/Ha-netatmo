"""Support des Prises Connectées Legrand/Netatmo."""
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Types de prises reconnus
PLUG_TYPES = ["NLP", "Plug", "Socket", "PowerOutlet"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Configuration des prises connectées."""
    data_context = hass.data[DOMAIN][entry.entry_id]
    coordinator = data_context["coordinator"]
    data_handler = data_context["api"]

    entities = []
    
    for home_id, home in coordinator.data.items():
        if not home.modules: 
            continue
        
        for module_id, module in home.modules.items():
            mod_class = module.__class__.__name__
            
            if mod_class in PLUG_TYPES:
                entities.append(NetatmoPlug(coordinator, home_id, module_id, data_handler))
            
    async_add_entities(entities)


class NetatmoPlug(CoordinatorEntity, SwitchEntity):
    """Représentation d'une prise connectée Legrand."""

    def __init__(self, coordinator, home_id, module_id, data_handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._module_id = module_id
        self._handler = data_handler
        
        self._attr_unique_id = f"{module_id}-switch"
        
        module = self._get_module()
        if module and hasattr(module, "name"):
            self._attr_name = module.name
        else:
            self._attr_name = f"Prise {module_id}"
        
        self._is_on = False
        self._power_consumption = None
        
        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        """Informations sur l'appareil."""
        module = self._get_module()
        model_name = module.__class__.__name__ if module else "Legrand Plug"
        
        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model=model_name,
            suggested_area=self._attr_name,
        )

    @property
    def is_on(self) -> bool:
        """Retourne si la prise est allumée."""
        return self._is_on

    @property
    def current_power_w(self):
        """Retourne la consommation actuelle en watts si disponible."""
        return self._power_consumption

    @property
    def available(self) -> bool:
        """Vérifie si l'appareil est disponible."""
        module = self._get_module()
        if module and hasattr(module, "reachable"):
            return module.reachable
        return True

    def _get_module(self):
        """Récupère le module depuis les données du coordinateur."""
        try:
            return self.coordinator.data[self._home_id].modules[self._module_id]
        except (KeyError, AttributeError):
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Met à jour l'état quand le coordinateur se rafraîchit."""
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        """Met à jour les attributs depuis les données du coordinateur."""
        module = self._get_module()
        if not module: 
            return

        # Lecture état On/Off
        self._is_on = getattr(module, "on", False)
        
        # Lecture consommation électrique si disponible
        self._power_consumption = getattr(module, "power", None)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allume la prise."""
        self._is_on = True
        self.async_write_ha_state()
        await self._async_push_command(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Éteint la prise."""
        self._is_on = False
        self.async_write_ha_state()
        await self._async_push_command(False)

    async def _async_push_command(self, on_state):
        """Envoi la commande via setstate avec Bridge ID."""
        try:
            home = self._handler.account.homes[self._home_id]
            
            # Récupération de l'objet module pour trouver son bridge
            module = self._get_module()
            bridge_id = getattr(module, "bridge", None)

            module_data = {
                "id": self._module_id,
                "on": on_state
            }
            
            # Ajout du Bridge ID si disponible (nécessaire pour Zigbee)
            if bridge_id:
                module_data["bridge"] = bridge_id

            _LOGGER.debug(f"Commande Prise (Bridge={bridge_id}): {module_data}")
            
            # Utilisation du wrapper officiel
            await home.async_set_state({"modules": [module_data]})
            
        except Exception as e:
            _LOGGER.error(f"Erreur Prise: {e}")
            await self.coordinator.async_request_refresh()
