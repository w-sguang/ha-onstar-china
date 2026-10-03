"""胎压告警等 binary_sensor。"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import build_device_info

_LOGGER = logging.getLogger(__name__)

TIRES = [
    ("LF", "左前"),
    ("RF", "右前"),
    ("LR", "左后"),
    ("RR", "右后"),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    vehicle = hass.data[DOMAIN][entry.entry_id].get("vehicle")
    async_add_entities([OnStarTirePressure(coordinator, entry, vehicle)])


class OnStarTirePressure(CoordinatorEntity, BinarySensorEntity):
    """任一胎压非正常（车辆上报状态不是 GREEN）时 on。"""

    _attr_has_entity_name = True
    _attr_name = "胎压告警"
    _attr_icon = "mdi:tire"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry: ConfigEntry,
                 vehicle: dict | None = None) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['vin']}_tire_warning"
        self._attr_device_info = build_device_info(entry.data["vin"], vehicle)

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        for code, _ in TIRES:
            item = data.get(f"TIRE PRESSURE {code}") or {}
            msg = (item.get("message") or "").strip().upper()
            if msg and msg != "GREEN":
                return True
        return False

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        attrs = {}
        for code, label in TIRES:
            item = data.get(f"TIRE PRESSURE {code}") or {}
            if item:
                attrs[label] = f"{item.get('value')} {item.get('unit', 'kPa')}"
        return attrs
