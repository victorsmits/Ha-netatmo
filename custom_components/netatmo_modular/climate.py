import time
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.components.climate.const import PRESET_AWAY, PRESET_ECO, PRESET_COMFORT, PRESET_NONE
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, NETATMO_MODE_SCHEDULE, NETATMO_MODE_MANUAL, NETATMO_MODE_OFF, NETATMO_MODE_AWAY, NETATMO_MODE_HG

VAL_COMFORT = "comfort"
VAL_ECO = "away"
VAL_HG = "frost_guard"
MANUAL_DURATION = 43200 

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    handler = data["api"]
    entities = []

    for home_id, home in coord.data.items():
        if not home.rooms: continue
        for room_id, room in home.rooms.items():
            if hasattr(room, "modules") and room.modules:
                if any(m.__class__.__name__ == "NLC" for m in room.modules.values()):
                    entities.append(NetatmoRoom(coord, home_id, room_id, handler))
            
    async_add_entities(entities)

class NetatmoRoom(CoordinatorEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, home_id, room_id, handler):
        super().__init__(coordinator)
        self._home_id = home_id
        self._room_id = room_id
        self._handler = handler
        self._attr_unique_id = f"{home_id}-{room_id}"
        self._attr_name = self.coordinator.data[home_id].rooms[room_id].name
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_preset_mode = PRESET_NONE
        self._update_local_state()

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
        self._update_local_state()
        self.async_write_ha_state()

    def _update_local_state(self):
        try:
            room = self.coordinator.data[self._home_id].rooms[self._room_id]
        except Exception:
            return

        mode = getattr(room, "therm_setpoint_mode", NETATMO_MODE_SCHEDULE)
        fp = getattr(room, "therm_setpoint_fp", None)

        if mode == NETATMO_MODE_OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = PRESET_NONE
        elif mode == NETATMO_MODE_SCHEDULE or mode == "home":
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE
        elif mode == NETATMO_MODE_HG:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_AWAY
        elif mode == NETATMO_MODE_AWAY:
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_preset_mode = PRESET_ECO
        elif mode == NETATMO_MODE_MANUAL:
            self._attr_hvac_mode = HVACMode.HEAT
            if fp == VAL_ECO: self._attr_preset_mode = PRESET_ECO
            elif fp == VAL_HG: self._attr_preset_mode = PRESET_AWAY
            else: self._attr_preset_mode = PRESET_COMFORT
        else:
            self._attr_hvac_mode = HVACMode.AUTO
            self._attr_preset_mode = PRESET_NONE

    async def _push(self, mode, fp=None):
        try:
            home = self._handler.account.homes[self._home_id]
            payload = {"id": self._room_id, "therm_setpoint_mode": mode}
            if mode == NETATMO_MODE_MANUAL:
                if fp: payload["therm_setpoint_fp"] = fp
                payload["therm_setpoint_temperature"] = 19
                payload["therm_setpoint_end_time"] = int(time.time() + MANUAL_DURATION)
            
            await home.async_set_state({"rooms": [payload]})
        except Exception:
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT: self._attr_preset_mode = PRESET_NONE
        self.async_write_ha_state()

        if hvac_mode == HVACMode.OFF: await self._push(NETATMO_MODE_OFF)
        elif hvac_mode == HVACMode.AUTO: await self._push("home")
        elif hvac_mode == HVACMode.HEAT:
            self._attr_preset_mode = PRESET_COMFORT
            await self._push(NETATMO_MODE_MANUAL, VAL_COMFORT)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._attr_preset_mode = preset_mode
        self._attr_hvac_mode = HVACMode.HEAT
        self.async_write_ha_state()

        if preset_mode == PRESET_NONE:
            await self.async_set_hvac_mode(HVACMode.AUTO)
            return

        tgt = VAL_COMFORT
        if preset_mode == PRESET_ECO: tgt = VAL_ECO
        elif preset_mode == PRESET_AWAY: tgt = VAL_HG
        
        await self._push(NETATMO_MODE_MANUAL, tgt)