"""Support Netatmo Fil Pilote - Stable, Optimiste & Anti-Rebond."""
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
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN, NETATMO_MODE_SCHEDULE, NETATMO_MODE_MANUAL, NETATMO_MODE_OFF

_LOGGER = logging.getLogger(__name__)

# Mapping
NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"
NETATMO_VAL_FROST_GUARD = "frost_guard"

DEFAULT_MANUAL_DURATION = 43200 
# Temps en secondes pendant lequel on ignore l'API après une commande
UPDATE_DEBOUNCE_SECONDS = 30

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data_handler = hass.data[DOMAIN][entry.entry_id]
    
    async def async_update_data():
        await data_handler.async_update()
        return data_handler.homes_data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="netatmo_climate_frozen", update_method=async_update_data
    )
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for home_id, home in coordinator.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
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
        
        self._attr_unique_id = f"{home_id}-{room_id}"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name
        
        # Pour gérer le délai de mise à jour API
        self._last_change_time = 0
        
        # Initialisation de l'état local
        self._update_attrs_from_coordinator()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Appelé quand l'API Netatmo renvoie de nouvelles données."""
        # --- FIX: LOGIQUE ANTI-REBOND ---
        # Si on a envoyé une commande il y a moins de 30 secondes,
        # on ignore la mise à jour API (qui contient surement encore l'ancien état).
        time_since_change = time.time() - self._last_change_time
        if time_since_change < UPDATE_DEBOUNCE_SECONDS:
            _LOGGER.debug(f"Ignorer update API (Debounce actif encore {int(UPDATE_DEBOUNCE_SECONDS - time_since_change)}s)")
            return

        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _update_attrs_from_coordinator(self):
        """Lit l'état réel depuis l'API."""
        try:
            room = self.coordinator.data[self._home_id].rooms[self._room_id]
        except (KeyError, AttributeError):
            return

        # Calcul HVAC Mode
        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        if mode == NETATMO_MODE_SCHEDULE or mode == "home":
            self._attr_hvac_mode = HVACMode.AUTO
        elif mode == NETATMO_MODE_OFF:
            self._attr_hvac_mode = HVACMode.OFF
        else:
            self._attr_hvac_mode = HVACMode.HEAT

        # Calcul Preset Mode
        self._attr_preset_mode = PRESET_NONE
        if self._attr_hvac_mode == HVACMode.HEAT:
            fp_val = getattr(room, "therm_setpoint_fp", None)
            if fp_val == NETATMO_VAL_COMFORT:
                self._attr_preset_mode = PRESET_COMFORT
            elif fp_val == NETATMO_VAL_ECO_MAPPED:
                self._attr_preset_mode = PRESET_ECO
            elif fp_val == NETATMO_VAL_FROST_GUARD:
                self._attr_preset_mode = PRESET_AWAY

    async def _async_push_pyatmo(self, mode_name, fp_val=None):
        """Pousse l'état."""
        try:
            home = self._handler.account.homes[self._home_id]
            
            room_payload = {
                "id": self._room_id,
                "therm_setpoint_mode": mode_name
            }
            
            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val:
                    room_payload["therm_setpoint_fp"] = fp_val
                room_payload["therm_setpoint_end_time"] = int(time.time() + DEFAULT_MANUAL_DURATION)

            _LOGGER.debug(f"Action UI -> API: {room_payload}")
            
            await home.async_set_state({"rooms": [room_payload]})
            
        except Exception as e:
            _LOGGER.error(f"Erreur Pyatmo: {e}")
            # En cas d'erreur technique, on annule le debounce pour re-synchroniser tout de suite
            self._last_change_time = 0 
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # 1. Enregistrement du moment de l'action (Début du Gel)
        self._last_change_time = time.time()

        # 2. Mise à jour Optimiste Locale
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT:
             self._attr_preset_mode = PRESET_NONE
        
        self.async_write_ha_state()

        # 3. Envoi Réseau
        if hvac_mode == HVACMode.OFF:
            await self._async_push_pyatmo(NETATMO_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_push_pyatmo("home")
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, NETATMO_VAL_COMFORT)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        # 1. Enregistrement du moment de l'action
        self._last_change_time = time.time()

        # 2. Mise à jour Optimiste
        self._attr_preset_mode = preset_mode
        self._attr_hvac_mode = HVACMode.HEAT
        self.async_write_ha_state()

        # 3. Envoi Réseau
        if preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return

        target = None
        if preset_mode == PRESET_COMFORT: target = NETATMO_VAL_COMFORT
        elif preset_mode == PRESET_ECO: target = NETATMO_VAL_ECO_MAPPED 
        elif preset_mode == PRESET_AWAY: target = NETATMO_VAL_FROST_GUARD

        if target:
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, target)