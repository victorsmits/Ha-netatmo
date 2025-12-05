"""Support Netatmo Fil Pilote - HomeKit Friendly (Cool = Eco)."""
import logging
import time
from datetime import timedelta

from homeassistant.components.climate import (
    ClimateEntity, ClimateEntityFeature, HVACMode
)
from homeassistant.components.climate.const import (
    PRESET_AWAY, PRESET_ECO, PRESET_COMFORT, PRESET_NONE
)
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, 
    NETATMO_MODE_SCHEDULE, 
    NETATMO_MODE_MANUAL, 
    NETATMO_MODE_OFF,
    NETATMO_MODE_AWAY,
    NETATMO_MODE_HG
)

_LOGGER = logging.getLogger(__name__)

# --- MAPPING VALEURS ---
NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"        # Eco = away dans l'API Legrand
NETATMO_VAL_FROST_GUARD = "frost_guard"

DEFAULT_MANUAL_DURATION = 43200 

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data_context = hass.data[DOMAIN][entry.entry_id]
    coordinator = data_context["coordinator"]
    data_handler = data_context["api"]

    entities = []
    for home_id, home in coordinator.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
            if hasattr(room, "name"):
                # Filtrage strict NLC
                is_radiator = False
                if hasattr(room, "modules") and room.modules:
                    for mod in room.modules.values():
                        if mod.__class__.__name__ == "NLC":
                            is_radiator = True
                            break
                
                if is_radiator:
                    entities.append(NetatmoRoomFilPilote(coordinator, home_id, room_id, data_handler))
            
    async_add_entities(entities)


class NetatmoRoomFilPilote(CoordinatorEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    
    # On garde les presets pour HA, mais on active aussi les modes ON/OFF pour HomeKit
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON | 
        ClimateEntityFeature.TURN_OFF | 
        ClimateEntityFeature.PRESET_MODE
    )
    
    # LISTE DES MODES : On inclut COOL pour le mapping Eco
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
    
    # Les vrais presets pour l'affichage HA
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
    
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, home_id, room_id, data_handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._handler = data_handler
        
        self._attr_unique_id = f"{home_id}-{room_id}"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name
        
        # Init par défaut
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_preset_mode = PRESET_NONE
        
        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model="Sortie de Câble Connectée (NLC)",
            suggested_area=self._attr_name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        """Traduction API Netatmo -> Modes HA Hybrides."""
        try:
            room = self.coordinator.data[self._home_id].rooms[self._room_id]
        except (KeyError, AttributeError):
            return

        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        fp_val = getattr(room, "therm_setpoint_fp", None)

        # 1. MODE AUTO (Planning)
        if mode == NETATMO_MODE_SCHEDULE or mode == "home":
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE
        
        # 2. MODE OFF (Vrai Off ou Hors-Gel global)
        elif mode == NETATMO_MODE_OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_NONE
            
        elif mode == NETATMO_MODE_HG:
            # Si toute la maison est HG, on l'affiche comme OFF pour simplifier
            # Ou comme HEAT + Away selon ta préférence. Ici OFF pour cohérence HomeKit.
            self._attr_hvac_mode = HVACMode.OFF 
            self._attr_preset_mode = PRESET_AWAY

        # 3. MODE MANUEL (Gestion du Hack Cool)
        elif mode == NETATMO_MODE_MANUAL or mode == NETATMO_MODE_AWAY:
            
            if fp_val == NETATMO_VAL_ECO_MAPPED or mode == NETATMO_MODE_AWAY:
                # C'est du ECO -> On active le mode COOL (Bleu)
                self._attr_hvac_mode = HVACMode.COOL
                self._attr_preset_mode = PRESET_ECO
                
            elif fp_val == NETATMO_VAL_FROST_GUARD:
                # C'est du Hors-Gel -> On active le mode OFF (Gris)
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_preset_mode = PRESET_AWAY
                
            else:
                # C'est du Confort -> On active le mode HEAT (Orange)
                self._attr_hvac_mode = HVACMode.HEAT
                self._attr_preset_mode = PRESET_COMFORT
        
        else:
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE

    async def _async_push_pyatmo(self, mode_name, fp_val=None):
        try:
            home = self._handler.account.homes[self._home_id]
            room_payload = {"id": self._room_id, "therm_setpoint_mode": mode_name}
            
            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val:
                    room_payload["therm_setpoint_fp"] = fp_val
                # Température fictive pour validation API
                room_payload["therm_setpoint_temperature"] = 19
                room_payload["therm_setpoint_end_time"] = int(time.time() + DEFAULT_MANUAL_DURATION)

            _LOGGER.debug(f"Cmd: {room_payload}")
            await home.async_set_state({"rooms": [room_payload]})
            
        except Exception as e:
            _LOGGER.error(f"Erreur envoi: {e}")
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Pilotage via Modes (Compatible HomeKit)."""
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

        if hvac_mode == HVACMode.OFF:
            # Bouton "Eteindre" HomeKit -> Envoie Hors-Gel (Sécurité)
            self._attr_preset_mode = PRESET_AWAY
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_FROST_GUARD)
            
        elif hvac_mode == HVACMode.AUTO:
            # Bouton "Auto" HomeKit -> Envoie Planning
            self._attr_preset_mode = PRESET_NONE
            await self._async_push_pyatmo("home")
            
        elif hvac_mode == HVACMode.HEAT:
            # Bouton "Chauffage" HomeKit -> Envoie Confort
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_COMFORT)
            
        elif hvac_mode == HVACMode.COOL:
            # Bouton "Clim" HomeKit -> Envoie ECO
            self._attr_preset_mode = PRESET_ECO
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_ECO_MAPPED)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Pilotage via Presets (Dashboard HA)."""
        self._attr_preset_mode = preset_mode
        
        # On met à jour le mode HVAC correspondant pour rester cohérent
        if preset_mode == PRESET_ECO:
            self._attr_hvac_mode = HVACMode.COOL
        elif preset_mode == PRESET_AWAY:
            self._attr_hvac_mode = HVACMode.OFF
        elif preset_mode == PRESET_NONE:
            self._attr_hvac_mode = HVACMode.AUTO
        else:
            self._attr_hvac_mode = HVACMode.HEAT
            
        self.async_write_ha_state()

        if preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return

        target = None
        if preset_mode == PRESET_COMFORT: target = NETATMO_VAL_COMFORT
        elif preset_mode == PRESET_ECO: target = NETATMO_VAL_ECO_MAPPED 
        elif preset_mode == PRESET_AWAY: target = NETATMO_VAL_FROST_GUARD

        if target:
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, target)