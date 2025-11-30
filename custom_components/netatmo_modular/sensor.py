from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

@dataclass(frozen=True)
class NetatmoSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[Any], Any] | None = None
    available_fn: Callable[[Any], bool] | None = None

ROOM_SENSOR_DESCRIPTIONS: tuple[NetatmoSensorEntityDescription, ...] = (
    NetatmoSensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda room: room.therm_measured_temperature,
    ),
    NetatmoSensorEntityDescription(
        key="target_temperature",
        name="Target Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda room: room.therm_setpoint_temperature,
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
        value_fn=lambda room: room.therm_setpoint_mode,
        icon="mdi:thermostat",
    ),
)

MODULE_SENSOR_DESCRIPTIONS: tuple[NetatmoSensorEntityDescription, ...] = (
    NetatmoSensorEntityDescription(
        key="battery_level",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mod: getattr(mod, "battery_level", None),
        available_fn=lambda mod: getattr(mod, "battery_level", None) is not None,
    ),
    NetatmoSensorEntityDescription(
        key="rf_strength",
        name="RF Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mod: getattr(mod, "rf_strength", None),
        available_fn=lambda mod: getattr(mod, "rf_strength", None) is not None,
    ),
    NetatmoSensorEntityDescription(
        key="wifi_strength",
        name="WiFi Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mod: getattr(mod, "wifi_strength", None),
        available_fn=lambda mod: getattr(mod, "wifi_strength", None) is not None,
    ),
    NetatmoSensorEntityDescription(
        key="boiler_status",
        name="Boiler Status",
        value_fn=lambda mod: "on" if getattr(mod, "boiler_status", False) else "off",
        available_fn=lambda mod: getattr(mod, "boiler_status", None) is not None,
        icon="mdi:water-boiler",
    ),
    NetatmoSensorEntityDescription(
        key="reachable",
        name="Reachable",
        value_fn=lambda mod: "yes" if getattr(mod, "reachable", True) else "no",
        icon="mdi:wifi",
    ),
)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for home in coordinator.homes.values():
        for room in home.rooms.values():
            for description in ROOM_SENSOR_DESCRIPTIONS:
                if description.value_fn(room) is not None:
                    entities.append(NetatmoRoomSensor(coordinator, room.entity_id, description, home.entity_id))
        for module in home.modules.values():
            for description in MODULE_SENSOR_DESCRIPTIONS:
                if description.available_fn and not description.available_fn(module): continue
                if description.value_fn(module) is None: continue
                entities.append(NetatmoModuleSensor(coordinator, module.entity_id, description, home.entity_id))
    async_add_entities(entities)

class NetatmoRoomSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, room_id, description, home_id):
        super().__init__(coordinator)
        self._room_id = room_id
        self._home_id = home_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_{room_id}_{description.key}"

    @property
    def _room(self):
        return self.coordinator.get_room(self._room_id)

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._room_id)}, "name": self._room.name, "manufacturer": "Netatmo", "via_device": (DOMAIN, self._home_id)}

    @property
    def native_value(self):
        return self.entity_description.value_fn(self._room) if self._room else None

class NetatmoModuleSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, module_id, description, home_id):
        super().__init__(coordinator)
        self._module_id = module_id
        self._home_id = home_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_{module_id}_{description.key}"

    @property
    def _module(self):
        return self.coordinator.get_module(self._module_id)

    @property
    def device_info(self):
        mod = self._module
        return {"identifiers": {(DOMAIN, self._module_id)}, "name": mod.name, "manufacturer": "Netatmo", "model": getattr(mod, "device_type", "Unknown"), "via_device": (DOMAIN, self._home_id)}

    @property
    def native_value(self):
        return self.entity_description.value_fn(self._module) if self._module else None