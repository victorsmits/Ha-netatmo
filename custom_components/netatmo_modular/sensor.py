"""Sensor platform for Netatmo Modular integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NetatmoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class NetatmoSensorEntityDescription(SensorEntityDescription):
    """Describes a Netatmo sensor entity."""
    value_fn: Callable[[Any], Any] | None = None
    available_fn: Callable[[Any], bool] | None = None

# Room sensors
ROOM_SENSOR_DESCRIPTIONS: tuple[NetatmoSensorEntityDescription, ...] = (
    NetatmoSensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda room: getattr(room, "therm_measured_temperature", None),
    ),
    NetatmoSensorEntityDescription(
        key="target_temperature",
        name="Target Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda room: getattr(room, "therm_setpoint_temperature", None),
    ),
    NetatmoSensorEntityDescription(
        key="heating_power",
        name="Heating Power Request",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda room: getattr(room, "heating_power_request", 0),
        icon="mdi:fire",
    ),
    NetatmoSensorEntityDescription(
        key="setpoint_mode",
        name="Setpoint Mode",
        value_fn=lambda room: getattr(room, "therm_setpoint_mode", None),
        icon="mdi:thermostat",
    ),
)

# Module sensors
MODULE_SENSOR_DESCRIPTIONS: tuple[NetatmoSensorEntityDescription, ...] = (
    NetatmoSensorEntityDescription(
        key="battery_level",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mod: getattr(mod, "battery_level", None),
    ),
    NetatmoSensorEntityDescription(
        key="rf_strength",
        name="RF Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mod: getattr(mod, "rf_strength", None),
    ),
    NetatmoSensorEntityDescription(
        key="wifi_strength",
        name="WiFi Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mod: getattr(mod, "wifi_strength", None),
    ),
    NetatmoSensorEntityDescription(
        key="boiler_status",
        name="Boiler Status",
        value_fn=lambda mod: "on" if getattr(mod, "boiler_status", False) else "off",
        icon="mdi:water-boiler",
    ),
    NetatmoSensorEntityDescription(
        key="reachable",
        name="Reachable",
        value_fn=lambda mod: "yes" if getattr(mod, "reachable", True) else "no",
        icon="mdi:wifi",
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo sensor entities."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    # Create room sensors
    for home in coordinator.homes.values():
        for room in home.rooms.values():
            for description in ROOM_SENSOR_DESCRIPTIONS:
                # MODIFICATION : On ajoute l'entité TOUJOURS, sans vérifier la valeur
                entities.append(
                    NetatmoRoomSensor(coordinator, room.entity_id, description, home.entity_id)
                )

        # Create module sensors
        for module in home.modules.values():
            for description in MODULE_SENSOR_DESCRIPTIONS:
                # MODIFICATION : Idem, on crée l'entité
                entities.append(
                    NetatmoModuleSensor(coordinator, module.entity_id, description, home.entity_id)
                )

    async_add_entities(entities)

class NetatmoRoomSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Netatmo room sensor."""
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NetatmoDataUpdateCoordinator,
        room_id: str,
        description: NetatmoSensorEntityDescription,
        home_id: str
    ) -> None:
        super().__init__(coordinator)
        self._room_id = room_id
        self._home_id = home_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_{room_id}_{description.key}"

    @property
    def _room(self):
        """Get pyatmo room object."""
        return self.coordinator.get_room(self._room_id)

    @property
    def device_info(self) -> DeviceInfo:
        room = self._room
        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=room.name if room else "Unknown Room",
            manufacturer="Netatmo",
            via_device=(DOMAIN, self._home_id),
        )

    @property
    def native_value(self) -> Any:
        room = self._room
        if not room:
            return None
        return self.entity_description.value_fn(room)


class NetatmoModuleSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Netatmo module sensor."""
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NetatmoDataUpdateCoordinator,
        module_id: str,
        description: NetatmoSensorEntityDescription,
        home_id: str
    ) -> None:
        super().__init__(coordinator)
        self._module_id = module_id
        self._home_id = home_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_{module_id}_{description.key}"

    @property
    def _module(self):
        return self.coordinator.get_module(self._module_id)

    @property
    def device_info(self) -> DeviceInfo:
        module = self._module
        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=module.name if module else "Unknown Module",
            manufacturer="Netatmo",
            model=getattr(module, "device_type", "Unknown"),
            via_device=(DOMAIN, self._home_id),
        )

    @property
    def native_value(self) -> Any:
        module = self._module
        if not module:
            return None
        return self.entity_description.value_fn(module)