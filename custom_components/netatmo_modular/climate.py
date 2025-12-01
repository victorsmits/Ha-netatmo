"""Support pour les thermostats Netatmo."""
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity, \
    DataUpdateCoordinator

from .const import (
    DOMAIN,
    NETATMO_MODE_SCHEDULE,
    NETATMO_MODE_MANUAL,
    NETATMO_MODE_OFF,
    NETATMO_MODE_AWAY,
    NETATMO_MODE_HG
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback):
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

    # Parcours de toutes les maisons (Multi-home)
    for home_id, home in coordinator.data.items():
        if not home.rooms:
            continue

        for room_id, room in home.rooms.items():
            # Filtrage des pièces sans capacité de chauffage
            if not getattr(room, "therm_setpoint_mode", None):
                continue

            entities.append(
                NetatmoRoomClimate(coordinator, home_id, room_id, data_handler))

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

        # Récupération du nom
        room_data = self.coordinator.data[home_id].rooms[room_id]
        self._attr_name = room_data.name

    @property
    def current_temperature(self):
        """Température actuelle."""
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        return room.therm_measured_temp

    @property
    def target_temperature(self):
        """Température cible."""
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        return room.therm_setpoint_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Mode HVAC."""
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        mode = room.therm_setpoint_mode

        if mode == NETATMO_MODE_SCHEDULE:
            return HVACMode.AUTO
        elif mode == NETATMO_MODE_MANUAL:
            return HVACMode.HEAT
        elif mode == NETATMO_MODE_OFF:
            return HVACMode.OFF
        # Par défaut si mode 'hg' ou 'away' -> Auto du point de vue HA Climate standard
        # mais le preset prendra le dessus visuellement
        return HVACMode.AUTO

    @property
    def preset_mode(self) -> Optional[str]:
        """Preset Mode."""
        room = self.coordinator.data[self._home_id].rooms[self._room_id]
        mode = room.therm_setpoint_mode

        if mode == NETATMO_MODE_AWAY:
            return PRESET_AWAY
        if mode == NETATMO_MODE_HG:
            return PRESET_ECO
        if mode == NETATMO_MODE_MANUAL:
            # Parfois Manual est considéré comme Comfort, ou None
            return PRESET_NONE
        return PRESET_NONE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode avec Optimistic Update."""
        old_mode = self._attr_hvac_mode
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()  # UI Update immédiate

        try:
            if hvac_mode == HVACMode.HEAT:
                # Mode MANUEL: Nécessite une temp cible. On garde la courante ou defaut 19
                target = self.target_temperature or 19
                await self._handler.account.async_set_room_thermpoint(
                    self._home_id, self._room_id, mode=NETATMO_MODE_MANUAL,
                    temp=target
                )
            elif hvac_mode == HVACMode.OFF:
                await self._handler.account.async_set_room_thermpoint(
                    self._home_id, self._room_id, mode=NETATMO_MODE_OFF
                )
            elif hvac_mode == HVACMode.AUTO:
                # Retour planning
                await self._handler.account.async_set_room_thermpoint(
                    self._home_id, self._room_id, mode="home"
                    # 'home' repasse en schedule pour la pièce
                )

            await self.coordinator.async_request_refresh()

        except Exception as e:
            self._attr_hvac_mode = old_mode
            self.async_write_ha_state()
            _LOGGER.error("Erreur set_hvac_mode: %s", e)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set Preset avec Optimistic Update."""
        old_preset = self._attr_preset_mode
        self._attr_preset_mode = preset_mode
        self.async_write_ha_state()

        try:
            # Note: Away et Frost Guard (HG) s'appliquent à TOUTE la maison chez Netatmo
            if preset_mode == PRESET_AWAY:
                await self._handler.account.async_set_home_thermmode(
                    self._home_id, mode=NETATMO_MODE_AWAY
                )
            elif preset_mode == PRESET_ECO:  # Frost Guard
                await self._handler.account.async_set_home_thermmode(
                    self._home_id, mode=NETATMO_MODE_HG
                )
            elif preset_mode == PRESET_NONE:
                # Annuler le preset revient à repasser en planning (schedule)
                await self._handler.account.async_set_home_thermmode(
                    self._home_id, mode=NETATMO_MODE_SCHEDULE
                )

            await self.coordinator.async_request_refresh()

        except Exception as e:
            self._attr_preset_mode = old_preset
            self.async_write_ha_state()
            _LOGGER.error("Erreur set_preset_mode: %s", e)

    async def async_set_temperature(self, **kwargs) -> None:
        """Changement de température (passe automatiquement en manuel)."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        try:
            await self._handler.account.async_set_room_thermpoint(
                self._home_id, self._room_id, mode=NETATMO_MODE_MANUAL,
                temp=temp
            )
            # Optimistic update de la target temp
            # Attention: c'est plus complexe à simuler car l'objet room est dans le coordinator
            # On laisse le refresh faire le travail pour la valeur précise,
            # mais on peut mettre à jour l'état UI si besoin.
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Erreur set_temperature: %s", e)