"""Support Netatmo Fil Pilote - Final UI & Logic Fix."""
import logging
import time
from typing import Optional

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
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

# Import des constantes depuis const.py
from .const import (
    DOMAIN, 
    NETATMO_MODE_SCHEDULE, 
    NETATMO_MODE_MANUAL, 
    NETATMO_MODE_OFF,
    NETATMO_MODE_AWAY,
    NETATMO_MODE_HG
)

_LOGGER = logging.getLogger(__name__)

# --- VALEURS API ---
NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"        # Eco = away dans l'API Legrand
NETATMO_VAL_FROST_GUARD = "frost_guard"

DEFAULT_MANUAL_DURATION = 43200 

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data_handler = hass.data[DOMAIN][entry.entry_id]
    
    async def async_update_data():
        await data_handler.async_update()
        return data_handler.homes_data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="netatmo_climate_ui", update_method=async_update_data
    )
    # Premier chargement des données
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for home_id, home in coordinator.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
            # On vérifie qu'on a bien affaire à une pièce valide
            if hasattr(room, "name"):
                entities.append(NetatmoRoomFilPilote(coordinator, home_id, room_id, data_handler))
            
    async_add_entities(entities)


class NetatmoRoomFilPilote(CoordinatorEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, home_id, room_id, data_handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._handler = data_handler
        
        # Identifiant unique stable
        self._attr_unique_id = f"{home_id}-{room_id}"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name
        
        # Initialisation de l'état
        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        """Informations pour le registre des appareils (Joli affichage)."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model="Sortie de Câble Connectée",
            via_device=(DOMAIN, self._home_id),
            suggested_area=self._attr_name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Mise à jour des données depuis l'API."""
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        """Logique de lecture de l'état (Parsing API)."""
        try:
            room = self.coordinator.data[self._home_id].rooms[self._room_id]
        except (KeyError, AttributeError):
            return

        # 1. Lecture du mode global
        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        fp_val = getattr(room, "therm_setpoint_fp", None)

        # 2. Déduction HVAC & Preset
        if mode == NETATMO_MODE_OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_NONE
            
        elif mode == NETATMO_MODE_SCHEDULE or mode == "home":
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE
            
        elif mode == NETATMO_MODE_HG:
            # Cas où la maison entière est en Hors Gel
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_AWAY
            
        elif mode == NETATMO_MODE_AWAY:
            # Cas où la maison entière est en Absent
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_ECO

        elif mode == NETATMO_MODE_MANUAL:
            # Mode Manuel : on regarde le Fil Pilote spécifique
            self._attr_hvac_mode = HVACMode.HEAT
            
            if fp_val == NETATMO_VAL_ECO_MAPPED: # 'away'
                self._attr_preset_mode = PRESET_ECO
            elif fp_val == NETATMO_VAL_FROST_GUARD: # 'frost_guard'
                self._attr_preset_mode = PRESET_AWAY
            elif fp_val == NETATMO_VAL_COMFORT:
                self._attr_preset_mode = PRESET_COMFORT
            else:
                # Si fp_val est vide ou inconnu en manuel, on garde le dernier état connu
                if self._attr_preset_mode == PRESET_NONE:
                    self._attr_preset_mode = PRESET_COMFORT
        else:
            # Fallback
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE

    async def _async_push_pyatmo(self, mode_name, fp_val=None):
        """Envoi de la commande via pyatmo (Structure Home > Rooms)."""
        try:
            home = self._handler.account.homes[self._home_id]
            
            room_payload = {
                "id": self._room_id,
                "therm_setpoint_mode": mode_name
            }
            
            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val:
                    room_payload["therm_setpoint_fp"] = fp_val
                # Temps obligatoire pour valider le manuel
                room_payload["therm_setpoint_end_time"] = int(time.time() + DEFAULT_MANUAL_DURATION)

            _LOGGER.debug(f"Commande envoyée: {room_payload}")
            
            # Utilisation de la méthode officielle
            await home.async_set_state({"rooms": [room_payload]})
            
            # Pas de refresh immédiat (Optimistic UI)
            
        except Exception as e:
            _LOGGER.error(f"Erreur envoi commande: {e}")
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Changement de mode principal."""
        # UI Optimiste
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT:
             self._attr_preset_mode = PRESET_NONE
        self.async_write_ha_state()

        # Envoi API
        if hvac_mode == HVACMode.OFF:
            await self._async_push_pyatmo(NETATMO_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_push_pyatmo("home") # "home" = planning pour la room
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_COMFORT)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Changement de preset."""
        # UI Optimiste
        self._attr_preset_mode = preset_mode
        self._attr_hvac_mode = HVACMode.HEAT
        self.async_write_ha_state()

        # Envoi API
        if preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return

        target = None
        if preset_mode == PRESET_COMFORT: target = NETATMO_VAL_COMFORT
        elif preset_mode == PRESET_ECO: target = NETATMO_VAL_ECO_MAPPED 
        elif preset_mode == PRESET_AWAY: target = NETATMO_VAL_FROST_GUARD

        if target:
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, target)