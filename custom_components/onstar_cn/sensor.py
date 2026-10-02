"""车况传感器。"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EVENT_COMMAND

_LOGGER = logging.getLogger(__name__)

# key -> (显示名, 诊断字段名, 单位, device_class, state_class)
SENSORS = [
    ("fuel_level", "油量", "FUEL LEVEL", "%", None, SensorStateClass.MEASUREMENT),
    ("fuel_amount", "油量(升)", "FUEL AMOUNT", "L", None, SensorStateClass.MEASUREMENT),
    ("fuel_capacity", "油箱容量", "FUEL CAPACITY", "L", None, SensorStateClass.MEASUREMENT),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        OnStarSensor(coordinator, entry, key, name, field, unit, dclass, sclass)
        for key, name, field, unit, dclass, sclass in SENSORS
    )
    async_add_entities([OnStarLastCommand(hass, entry)])


class OnStarSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, field, unit, dclass, sclass):
        super().__init__(coordinator)
        self._field = field
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dclass
        self._attr_state_class = sclass
        self._attr_unique_id = f"{entry.data['vin']}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["vin"])},
            "name": f"安吉星 {entry.data['vin'][-6:]}",
            "manufacturer": "OnStar China",
            "model": "上汽通用 OnStar 车辆",
        }

    @property
    def native_value(self):
        item = (self.coordinator.data or {}).get(self._field)
        if not item:
            return None
        try:
            return round(float(item["value"]), 2)
        except (TypeError, ValueError):
            return None


class OnStarLastCommand(SensorEntity):
    """显示最近一次远程指令的执行结果。"""

    _attr_has_entity_name = True
    _attr_name = "最后指令结果"
    _attr_icon = "mdi:history"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._attr_unique_id = f"{entry.data['vin']}_last_command"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["vin"])},
            "name": f"安吉星 {entry.data['vin'][-6:]}",
            "manufacturer": "OnStar China",
            "model": "上汽通用 OnStar 车辆",
        }
        self._state = "无"
        self._attrs: dict = {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_COMMAND, self._handle)
        )

    def _handle(self, event) -> None:
        d = event.data
        ok = d.get("success")
        self._state = "成功" if ok else "失败"
        self._attrs = {
            "指令": d.get("name"),
            "状态": d.get("status"),
            "信息": d.get("message") or "",
        }
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attrs
