"""Support Netatmo Fil Pilote - LECTURE MODULE DIRECT."""
import logging
import pprint
import time

from homeassistant.components.climate import (
    ClimateEntity, ClimateEntityFeature, HVACMode
)
from homeassistant.components.climate.const import (
    PRESET_AWAY, PRESET_ECO, PRESET_COMFORT, PRESET_NONE
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# Import des constantes
from .const import DOMAIN, NETATMO_MODE_MANUAL, NETATMO_MODE_OFF

_LOGGER = logging.getLogger(__name__)

# Valeurs API
NETATMO_VAL_COMFORT = "comfort"
NETATMO_VAL_ECO_MAPPED = "away"
NETATMO_VAL_FROST_GUARD = "frost_guard"
DEFAULT_MANUAL_DURATION = 43200


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback):
    data_context = hass.data[DOMAIN][entry.entry_id]
    coordinator = data_context["coordinator"]
    data_handler = data_context["api"]

    entities = []
    for home_id, home in coordinator.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
            if hasattr(room, "name"):
                entities.append(
                    NetatmoRoomFilPilote(coordinator, home_id, room_id,
                                         data_handler))

    _LOGGER.warning("--- DEBUG MODULE LECTURE ---")
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

        # Initialisation
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_preset_mode = PRESET_NONE

        self._update_attrs_from_coordinator()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=self._attr_name,
            manufacturer="Legrand/Netatmo",
            model="Sortie de Câble Connectée",
            suggested_area=self._attr_name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attrs_from_coordinator()
        self.async_write_ha_state()

    def _get_module(self):
        """Récupère l'objet module associé à la pièce."""
        try:
            home = self.coordinator.data[self._home_id]
            room = home.rooms[self._room_id]
            if hasattr(room, "module_ids") and room.module_ids:
                module_id = room.module_ids[0]
                return home.modules.get(module_id)
        except Exception:
            pass
        return None

    def _update_attrs_from_coordinator(self):
        """Lecture intelligente (Room + Module)."""
        module = self._get_module()

        # === DEBUG MODULE ===
        if module:
            try:
                # On dump le contenu du module
                # On utilise __dict__ pour voir les vraies variables internes
                dump = pprint.pformat(module.__dict__)
                _LOGGER.warning(f"🔍 MODULE DUMP {self._attr_name}:\n{dump}")
            except Exception as e:
                _LOGGER.error(f"Erreur dump module: {e}")
        else:
            _LOGGER.warning(f"⚠️ Aucun module trouvé pour {self._attr_name}")
        # ====================

        # On essaie de lire sur le module d'abord (plus fiable pour Legrand ?)
        # Sinon on fallback sur la room (via l'ancienne méthode)

        # NOTE: Je ne change pas la logique de lecture tout de suite pour ne pas tout casser,
        # j'attends de voir tes logs pour savoir quel champ utiliser (ex: 'fp_mode' sur le module ?)

        # Pour l'instant, on reste sur la lecture Room qui renvoie None
        # Ce qui explique pourquoi tu es en 'Inconnu' ou 'Auto' par défaut.

        # SI le dump nous montre un champ 'pilot_wire_mode' sur le module, on l'utilisera ici.

    async def _async_push_pyatmo(self, mode_name, fp_val=None):
        try:
            home = self._handler.account.homes[self._home_id]
            room_payload = {"id": self._room_id,
                            "therm_setpoint_mode": mode_name}

            if mode_name == NETATMO_MODE_MANUAL:
                if fp_val:
                    room_payload["therm_setpoint_fp"] = fp_val
                room_payload["therm_setpoint_temperature"] = 19
                room_payload["therm_setpoint_end_time"] = int(
                    time.time() + DEFAULT_MANUAL_DURATION)

            _LOGGER.debug(f"Commande envoyée: {room_payload}")
            await home.async_set_state({"rooms": [room_payload]})

        except Exception as e:
            _LOGGER.error(f"Erreur envoi commande: {e}")
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT: self._attr_preset_mode = PRESET_NONE
        self.async_write_ha_state()

        if hvac_mode == HVACMode.OFF:
            await self._async_push_pyatmo(NETATMO_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_push_pyatmo("home")
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL,
                                          NETATMO_VAL_COMFORT)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._attr_preset_mode = preset_mode
        self._attr_hvac_mode = HVACMode.HEAT
        self.async_write_ha_state()

        if preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return

        target = None
        if preset_mode == PRESET_COMFORT:
            target = NETATMO_VAL_COMFORT
        elif preset_mode == PRESET_ECO:
            target = NETATMO_VAL_ECO_MAPPED
        elif preset_mode == PRESET_AWAY:
            target = NETATMO_VAL_FROST_GUARD

        if target:
            await self._async_push_pyatmo(NETATMO_MODE_MANUAL, target)
