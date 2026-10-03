"""车况传感器。"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EVENT_COMMAND
from .entity import build_device_info, vehicle_display

_LOGGER = logging.getLogger(__name__)

# key, 显示名, 诊断字段名, 单位, device_class, state_class, 图标
SENSORS = [
    ("fuel_level", "油量", "FUEL LEVEL", "%", None,
     SensorStateClass.MEASUREMENT, "mdi:gas-station"),
    ("fuel_amount", "油量(升)", "FUEL AMOUNT", "L", None,
     SensorStateClass.MEASUREMENT, "mdi:gas-station"),
    ("fuel_capacity", "油箱容量", "FUEL CAPACITY", "L", None,
     SensorStateClass.MEASUREMENT, "mdi:gas-station-outline"),
    ("range", "剩余续航", "GAS RANGE", "km", SensorDeviceClass.DISTANCE,
     SensorStateClass.MEASUREMENT, "mdi:map-marker-distance"),
    ("odometer", "总里程", "ODOMETER", "km", SensorDeviceClass.DISTANCE,
     SensorStateClass.TOTAL_INCREASING, "mdi:counter"),
    ("oil_life", "机油寿命", "OIL LIFE", "%", None,
     SensorStateClass.MEASUREMENT, "mdi:oil"),
    ("tire_lf", "胎压 左前", "TIRE PRESSURE LF", "kPa",
     SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT, "mdi:tire"),
    ("tire_rf", "胎压 右前", "TIRE PRESSURE RF", "kPa",
     SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT, "mdi:tire"),
    ("tire_lr", "胎压 左后", "TIRE PRESSURE LR", "kPa",
     SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT, "mdi:tire"),
    ("tire_rr", "胎压 右后", "TIRE PRESSURE RR", "kPa",
     SensorDeviceClass.PRESSURE, SensorStateClass.MEASUREMENT, "mdi:tire"),
    ("last_trip_distance", "上次行程里程", "LAST TRIP TOTAL DISTANCE", "km",
     SensorDeviceClass.DISTANCE, None, "mdi:road-variant"),
    ("last_trip_econ", "上次行程油耗", "LAST TRIP FUEL ECON", "km/L", None,
     SensorStateClass.MEASUREMENT, "mdi:fuel"),
    ("lifetime_econ", "综合油耗", "LIFETIME FUEL ECON", "km/L", None,
     SensorStateClass.MEASUREMENT, "mdi:fuel"),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    vehicle = data.get("vehicle") or {}
    async_add_entities(
        OnStarSensor(coordinator, entry, vehicle, *spec) for spec in SENSORS
    )
    async_add_entities([
        OnStarVehicleInfo(entry, vehicle),
        OnStarLastCommand(hass, entry, vehicle),
    ])


class OnStarSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, vehicle, key, name, field, unit, dclass,
                 sclass, icon):
        super().__init__(coordinator)
        self._field = field
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dclass
        self._attr_state_class = sclass
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.data['vin']}_{key}"
        self._attr_device_info = build_device_info(entry.data["vin"], vehicle)

    @property
    def native_value(self):
        item = (self.coordinator.data or {}).get(self._field)
        if not item:
            return None
        try:
            return round(float(item["value"]), 2)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        item = (self.coordinator.data or {}).get(self._field) or {}
        attrs = {}
        msg = (item.get("message") or "").strip()
        if msg and msg.lower() != "na":
            attrs["状态"] = "正常" if msg.upper() == "GREEN" else msg
        meta = (self.coordinator.data or {}).get("_meta") or {}
        if meta.get("updated"):
            attrs["数据时间"] = meta["updated"]
        return attrs


class OnStarVehicleInfo(SensorEntity):
    """车辆品牌 / 车型 / 年款（来自 /suite 接口，静态信息）。"""

    _attr_has_entity_name = True
    _attr_name = "车辆信息"
    _attr_icon = "mdi:car-info"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, vehicle: dict | None) -> None:
        self._vehicle = vehicle or {}
        self._attr_unique_id = f"{entry.data['vin']}_vehicle_info"
        self._attr_device_info = build_device_info(entry.data["vin"], vehicle)

    @property
    def native_value(self):
        _, model = vehicle_display(self._vehicle)
        return model or None

    @property
    def extra_state_attributes(self):
        v = self._vehicle
        brand, _ = vehicle_display(v)
        attrs = {}
        if brand:
            attrs["品牌"] = brand
        if (v.get("brand") or "").strip():
            attrs["品牌代码"] = v["brand"].strip()
        if (v.get("seriesNameCN") or "").strip():
            attrs["车系"] = v["seriesNameCN"].strip()
        if (v.get("year") or "").strip():
            attrs["年款"] = v["year"].strip()
        if (v.get("makeDesc") or "").strip():
            attrs["制造商"] = v["makeDesc"].strip()
        if (v.get("generationDescription") or "").strip():
            attrs["车机世代"] = v["generationDescription"].strip()
        return attrs


class OnStarLastCommand(SensorEntity):
    """显示最近一次远程指令的执行结果。"""

    _attr_has_entity_name = True
    _attr_name = "最后指令结果"
    _attr_icon = "mdi:history"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry,
                 vehicle: dict | None = None) -> None:
        self.hass = hass
        self._attr_unique_id = f"{entry.data['vin']}_last_command"
        self._attr_device_info = build_device_info(entry.data["vin"], vehicle)
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
