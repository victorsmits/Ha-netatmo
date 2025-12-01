"""Support pour les thermostats Netatmo (Version DEBUG)."""
import logging
from typing import Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_COMFORT,
    PRESET_NONE,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import (
    DOMAIN,
    NETATMO_MODE_SCHEDULE,
    NETATMO_MODE_MANUAL,
    NETATMO_MODE_OFF,
    NETATMO_MODE_AWAY,
    NETATMO_MODE_HG
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Configuration des entités Climate."""
    data_handler = hass.data[DOMAIN][entry.entry_id]

    async def async_update_data():
        await data_handler.async_update()
        return data_handler.homes_data

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="netatmo_climate", update_method=async_update_data
    )
    await coordinator.async_config_entry_first_refresh()

    entities = []

    _LOGGER.warning("--- DÉBUT DU SCAN NETATMO ---")

    # Parcours de toutes les maisons
    if not coordinator.data:
        _LOGGER.error("Aucune donnée reçue du coordinateur !")
        return

    for home_id, home in coordinator.data.items():
        _LOGGER.warning(f"Scan de la maison : {home.name} (ID: {home_id})")

        if not home.rooms:
            _LOGGER.warning(f"La maison {home.name} n'a pas de pièces (rooms).")
            continue

        for room_id, room in home.rooms.items():
            _LOGGER.warning(f"Scan de la pièce : {room.name} (ID: {room_id})")

            # INSPECTION DES ATTRIBUTS (C'est ça qui va nous aider)
            # On liste tous les attributs disponibles sur l'objet room
            attrs = dir(room)
            values = {k: getattr(room, k) for k in attrs if not k.startswith('_') and not callable(getattr(room, k))}
            _LOGGER.warning(f"DATA BRUTE PIECE {room.name}: {values}")

            # TEST: On essaye de voir ce qui manque
            has_setpoint = getattr(room, "therm_setpoint_mode", None)
            has_temp = getattr(room, "therm_measured_temp", None)

            _LOGGER.warning(f"  -> therm_setpoint_mode: {has_setpoint}")
            _LOGGER.warning(f"  -> therm_measured_temp: {has_temp}")

            # J'ai relaxé le filtre : si on a une température OU un mode, on crée l'entité
            if has_setpoint is None and has_temp is None:
                 _LOGGER.warning(f"  -> IGNORÉ : Pas de données climatiques valides.")
                 # continue # Je commente le continue pour FORCER l'affichage pour le test

            entities.append(NetatmoRoomClimate(coordinator, home_id, room_id, data_handler))

    _LOGGER.warning(f"--- FIN DU SCAN : {len(entities)} entités trouvées ---")
    async_add_entities(entities)


class NetatmoRoomClimate(CoordinatorEntity, ClimateEntity):
    """Représentation d'une pièce Netatmo."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE |
        ClimateEntityFeature.PRESET_MODE |
        ClimateEntityFeature.TURN_ON |
        ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_NONE, PRESET_AWAY, PRESET_ECO, PRESET_COMFORT]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, home_id, room_id, data_handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._handler = data_handler
        self._attr_unique_id = f"{home_id}-{room_id}"

        room_data = self.coordinator.data[home_id].rooms[room_id]
        self._attr_name = room_data.name

    @property
    def current_temperature(self):
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        return getattr(room, "therm_measured_temp", None)

    @property
    def target_temperature(self):
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        return getattr(room, "therm_setpoint_temp", None)

    @property
    def hvac_mode(self) -> HVACMode:
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        # Utilisation de getattr pour éviter le crash si l'attribut manque
        mode = getattr(room, "therm_setpoint_mode", None)

        if mode == NETATMO_MODE_SCHEDULE:
            return HVACMode.AUTO
        elif mode == NETATMO_MODE_MANUAL:
            return HVACMode.HEAT
        elif mode == NETATMO_MODE_OFF:
            return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def preset_mode(self) -> Optional[str]:
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        mode = getattr(room, "therm_setpoint_mode", None)

        if mode == NETATMO_MODE_AWAY:
            return PRESET_AWAY
        if mode == NETATMO_MODE_HG:
            return PRESET_ECO
        return PRESET_NONE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        # Pour le test, on log juste l'action
        _LOGGER.warning(f"Demande changement mode vers {hvac_mode}")
        # ... Code d'action (gardé tel quel ou simplifié pour le debug) ...
        # Copie le reste de la fonction set_hvac_mode du fichier précédent si tu veux tester l'écriture
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        pass

    async def async_set_temperature(self, **kwargs) -> None:
        pass