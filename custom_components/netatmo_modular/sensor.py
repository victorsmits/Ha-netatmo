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

    value_fn: Callable[[dict[str, Any]], Any] | None = None
    available_fn: Callable[[dict[str, Any]], bool] | None = None


# Room sensors
ROOM_SENSOR_DESCRIPTIONS: tuple[NetatmoSensorEntityDescription, ...] = (
    NetatmoSensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("therm_measured_temperature"),
    ),
    NetatmoSensorEntityDescription(
        key="target_temperature",
        name="Target Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("therm_setpoint_temperature"),
    ),
    NetatmoSensorEntityDescription(
        key="heating_power",
        name="Heating Power Request",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("heating_power_request"),
        icon="mdi:fire",
    ),
    NetatmoSensorEntityDescription(
        key="setpoint_mode",
        name="Setpoint Mode",
        value_fn=lambda data: data.get("therm_setpoint_mode"),
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
        value_fn=lambda data: data.get("battery_level"),
        available_fn=lambda data: data.get("battery_level") is not None,
    ),
    NetatmoSensorEntityDescription(
        key="battery_state",
        name="Battery State",
        value_fn=lambda data: data.get("battery_state"),
        available_fn=lambda data: data.get("battery_state") is not None,
        icon="mdi:battery",
    ),
    NetatmoSensorEntityDescription(
        key="rf_strength",
        name="RF Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("rf_strength"),
        available_fn=lambda data: data.get("rf_strength") is not None,
    ),
    NetatmoSensorEntityDescription(
        key="wifi_strength",
        name="WiFi Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("wifi_strength"),
        available_fn=lambda data: data.get("wifi_strength") is not None,
    ),
    NetatmoSensorEntityDescription(
        key="boiler_status",
        name="Boiler Status",
        value_fn=lambda data: "on" if data.get("boiler_status") else "off",
        available_fn=lambda data: data.get("boiler_status") is not None,
        icon="mdi:water-boiler",
    ),
    NetatmoSensorEntityDescription(
        key="reachable",
        name="Reachable",
        value_fn=lambda data: "yes" if data.get("reachable", True) else "no",
        icon="mdi:wifi",
    ),
)

# Home sensors
HOME_SENSOR_DESCRIPTIONS: tuple[NetatmoSensorEntityDescription, ...] = (
    NetatmoSensorEntityDescription(
        key="therm_mode",
        name="Thermostat Mode",
        value_fn=lambda data: data.get("therm_mode"),
        icon="mdi:home-thermometer",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Netatmo sensor entities from a config entry."""
    coordinator: NetatmoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = []

    # Create room sensors
    for room_id, room in coordinator.rooms.items():
        for description in ROOM_SENSOR_DESCRIPTIONS:
            # Only create sensor if data is available
            if description.value_fn and description.value_fn(room) is not None:
                entities.append(
                    NetatmoRoomSensor(
                        coordinator=coordinator,
                        room_id=room_id,
                        description=description,
                    )
                )

    # Create module sensors
    for module_id, module in coordinator.modules.items():
        for description in MODULE_SENSOR_DESCRIPTIONS:
            # Check if this sensor type is available for this module
            if description.available_fn and not description.available_fn(module):
                continue
            if description.value_fn and description.value_fn(module) is None:
                continue

            entities.append(
                NetatmoModuleSensor(
                    coordinator=coordinator,
                    module_id=module_id,
                    description=description,
                )
            )

    # Create home sensors
    for home_id, home in coordinator.homes.items():
        for description in HOME_SENSOR_DESCRIPTIONS:
            if description.value_fn and description.value_fn(home) is not None:
                entities.append(
                    NetatmoHomeSensor(
                        coordinator=coordinator,
                        home_id=home_id,
                        description=description,
                    )
                )

    _LOGGER.info("Setting up %d Netatmo sensor entities", len(entities))
    async_add_entities(entities)


class NetatmoRoomSensor(CoordinatorEntity[NetatmoDataUpdateCoordinator], SensorEntity):
    """Representation of a Netatmo room sensor."""

    _attr_has_entity_name = True
    entity_description: NetatmoSensorEntityDescription

    def __init__(
        self,
        coordinator: NetatmoDataUpdateCoordinator,
        room_id: str,
        description: NetatmoSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._room_id = room_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_{room_id}_{description.key}"

    @property
    def _room(self) -> dict[str, Any]:
        """Get current room data."""
        return self.coordinator.get_room(self._room_id) or {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        home_name = self._room.get("home_name", "Netatmo Home")
        room_name = self._room.get("name", "Unknown Room")

        return DeviceInfo(
            identifiers={(DOMAIN, self._room_id)},
            name=f"{home_name} - {room_name}",
            manufacturer="Netatmo",
            model="Smart Thermostat Room",
            via_device=(DOMAIN, self._room.get("home_id", "")),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        if self._room_id not in self.coordinator.rooms:
            return False
        if self.entity_description.available_fn:
            return self.entity_description.available_fn(self._room)
        return True

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self._room)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class NetatmoModuleSensor(CoordinatorEntity[NetatmoDataUpdateCoordinator], SensorEntity):
    """Representation of a Netatmo module sensor."""

    _attr_has_entity_name = True
    entity_description: NetatmoSensorEntityDescription

    def __init__(
        self,
        coordinator: NetatmoDataUpdateCoordinator,
        module_id: str,
        description: NetatmoSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._module_id = module_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_{module_id}_{description.key}"

    @property
    def _module(self) -> dict[str, Any]:
        """Get current module data."""
        return self.coordinator.get_module(self._module_id) or {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        module_name = self._module.get("name", "Unknown Module")
        module_type = self._module.get("type", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, self._module_id)},
            name=module_name,
            manufacturer="Netatmo",
            model=module_type,
            via_device=(DOMAIN, self._module.get("home_id", "")),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        if self._module_id not in self.coordinator.modules:
            return False
        if self.entity_description.available_fn:
            return self.entity_description.available_fn(self._module)
        return True

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self._module)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class NetatmoHomeSensor(CoordinatorEntity[NetatmoDataUpdateCoordinator], SensorEntity):
    """Representation of a Netatmo home sensor."""

    _attr_has_entity_name = True
    entity_description: NetatmoSensorEntityDescription

    def __init__(
        self,
        coordinator: NetatmoDataUpdateCoordinator,
        home_id: str,
        description: NetatmoSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._home_id = home_id
        self.entity_description = description
        self._attr_unique_id = f"netatmo_modular_home_{home_id}_{description.key}"

    @property
    def _home(self) -> dict[str, Any]:
        """Get current home data."""
        return self.coordinator.homes.get(self._home_id) or {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        home_name = self._home.get("name", "Netatmo Home")

        return DeviceInfo(
            identifiers={(DOMAIN, self._home_id)},
            name=home_name,
            manufacturer="Netatmo",
            model="Smart Home",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        if self._home_id not in self.coordinator.homes:
            return False
        return True

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self._home)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
