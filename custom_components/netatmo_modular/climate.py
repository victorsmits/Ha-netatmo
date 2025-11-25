"""Climate platform for Netatmo Modular integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
# On importe les constantes standards
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ANTICIPATING,
    ATTR_BOILER_STATUS,
    ATTR_HEATING_POWER_REQUEST,
    ATTR_HOME_ID,
    ATTR_OPEN_WINDOW,
    ATTR_ROOM_ID,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    PRESET_MODES,
    TEMP_STEP,
)
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Mapping : Netatmo -> Standard HA (pour avoir les icônes)
NETATMO_TO_PRESET = {
    "manual": None,
    "max": PRESET_COMFORT,
    "frost_guard": PRESET_ECO,  # Frost Guard devient ECO (Feuille)
    "hg": PRESET_ECO,
    "off": PRESET_AWAY,
    "schedule": PRESET_HOME,    # Schedule devient HOME (Maison)
    "home": PRESET_HOME,
    "away": PRESET_AWAY,
    "comfort": PRESET_COMFORT,
    "eco": PRESET_AWAY,         # Le vrai Eco n'existe pas, on le map sur Away
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo climate entities."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[NetatmoClimate] = []

    for room_id, room in coordinator.rooms.items():
        if room.get("module_ids"):
            entities.append(NetatmoClimate(coordinator, room_id))

    async_add_entities(entities)


class NetatmoClimate(CoordinatorEntity[NetatmoDataUpdateCoordinator], ClimateEntity):
    """Representation of a Netatmo climate device."""

    _attr_has_entity_name = True
    _attr_translation_key = "netatmo_thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESET_MODES

    def __init__(self, coordinator: NetatmoDataUpdateCoordinator, room_id: str) -> None:
        super().__init__(coordinator)
        self._room_id = room_id
        self._attr_unique_id = f"netatmo_modular_climate_{room_id}"

    @property
    def _room(self) -> dict[str, Any]:
        return self.coordinator.get_room(self._room_id) or {}

    @property
    def _home(self) -> dict[str, Any]:
        return self.coordinator.get_home_for_room(self._room_id) or {}

    @property
    def name(self) -> str:
        return self._room.get("name", f"Room {self._room_id}")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=f"{self._room.get('home_name', 'Netatmo')} - {self.name}",
            manufacturer="Netatmo",
            model="Smart Thermostat Room",
            via_device=(DOMAIN, self._room.get("home_id", "")),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._room_id in self.coordinator.rooms

    @property
    def current_temperature(self) -> float | None:
        return self._room.get("therm_measured_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self._room.get("therm_setpoint_temperature")

    @property
    def hvac_mode(self) -> HVACMode:
        setpoint_mode = self._room.get("therm_setpoint_mode", "schedule")
        home_mode = self._home.get("therm_mode", "schedule")
        fp_mode = self._room.get("therm_setpoint_fp")

        if setpoint_mode in ("schedule", "home") or home_mode in ("schedule", "home"):
            return HVACMode.AUTO

        if setpoint_mode == "manual":
            if fp_mode in ("frost_guard", "hg"):
                return HVACMode.OFF
            return HVACMode.HEAT

        if setpoint_mode in ("off", "away", "frost_guard", "hg"):
            return HVACMode.OFF

        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        heating_power = self._room.get("heating_power_request")
        if heating_power is not None and heating_power > 0:
            return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        setpoint_mode = self._room.get("therm_setpoint_mode", "schedule")
        fp_mode = self._room.get("therm_setpoint_fp")

        if setpoint_mode == "schedule":
            return PRESET_HOME # Mappé sur HOME pour l'icone Maison

        if setpoint_mode == "manual":
            if fp_mode == "comfort":
                return PRESET_COMFORT
            elif fp_mode == "away":
                return PRESET_AWAY
            elif fp_mode in ("frost_guard", "hg"):
                return PRESET_ECO # Mappé sur ECO pour l'icone Feuille
            elif fp_mode == "eco":
                return PRESET_AWAY
        
        if setpoint_mode in ("frost_guard", "hg"):
            return PRESET_ECO
        if setpoint_mode == "away":
            return PRESET_AWAY

        return NETATMO_TO_PRESET.get(setpoint_mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {
            ATTR_HOME_ID: self._room.get("home_id"),
            ATTR_ROOM_ID: self._room_id,
            ATTR_HEATING_POWER_REQUEST: self._room.get("heating_power_request"),
            ATTR_ANTICIPATING: self._room.get("anticipating"),
            ATTR_OPEN_WINDOW: self._room.get("open_window"),
            "fil_pilote": self._room.get("therm_setpoint_fp"),
        }
        return {k: v for k, v in attrs.items() if v is not None}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        # Ici on reçoit le preset HA (ex: 'home' ou 'eco') et on doit envoyer le bon ordre à Netatmo
        if preset_mode == PRESET_HOME: # Si on clique sur Maison (Planning)
            await self.coordinator.async_set_room_mode(self._room_id, mode="schedule")
        
        elif preset_mode == PRESET_AWAY: # Si on clique sur Absent
            await self.coordinator.async_set_room_mode(self._room_id, mode="manual", fp="away")
        
        elif preset_mode == PRESET_ECO: # Si on clique sur Eco (Hors-gel)
            await self.coordinator.async_set_room_mode(self._room_id, mode="manual", fp="frost_guard")
        
        elif preset_mode == PRESET_COMFORT: # Si on clique sur Confort
            await self.coordinator.async_set_room_mode(self._room_id, mode="manual", fp="comfort")
        
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_set_preset_mode(PRESET_ECO) # Off lance Hors-gel
        elif hvac_mode == HVACMode.AUTO:
            await self.async_set_preset_mode(PRESET_HOME) # Auto lance Planning
        elif hvac_mode == HVACMode.HEAT:
            await self.async_set_preset_mode(PRESET_COMFORT) # Heat lance Confort

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()