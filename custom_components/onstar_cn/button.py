"""远程控制按钮。"""
from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OnStarApi
from .const import (
    CMD_CANCEL_FLASH, CMD_CANCEL_START, CMD_FLASH, CMD_START, DOMAIN, EVENT_COMMAND,
)

_LOGGER = logging.getLogger(__name__)

BUTTONS = [
    ("remote_start", "远程启动", CMD_START),
    ("cancel_start", "取消启动", CMD_CANCEL_START),
    ("flash_horn", "闪灯鸣笛", CMD_FLASH),
    ("cancel_flash", "取消闪灯鸣笛", CMD_CANCEL_FLASH),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    api: OnStarApi = hass.data[DOMAIN][entry.entry_id]["api"]
    async_add_entities(
        OnStarButton(hass, api, entry, key, name, cmd) for key, name, cmd in BUTTONS
    )


class OnStarButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, api: OnStarApi, entry: ConfigEntry,
                 key: str, name: str, cmd: str) -> None:
        self.hass = hass
        self._api = api
        self._cmd = cmd
        self._attr_name = name
        self._attr_unique_id = f"{entry.data['vin']}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["vin"])},
            "name": f"安吉星 {entry.data['vin'][-6:]}",
            "manufacturer": "OnStar China",
            "model": "上汽通用 OnStar 车辆",
        }

    async def async_press(self) -> None:
        _LOGGER.debug("按下 %s -> %s", self.name, self._cmd)
        await self._api.async_run(self._cmd)
        self._report()

    def _report(self) -> None:
        res = self._api.last_result or {}
        status = str(res.get("status", "unknown")).lower()
        ok = status in ("success", "succeeded")
        self.hass.bus.async_fire(EVENT_COMMAND, {
            "name": self.name, "cmd": self._cmd,
            "success": ok, "status": res.get("status"),
            "message": res.get("message"),
        })
        if not ok:
            persistent_notification.async_create(
                self.hass,
                f"「{self.name}」执行失败\n状态：{res.get('status')}\n信息：{res.get('message') or '无'}",
                title="安吉星指令失败",
                notification_id="onstar_cn_cmd",
            )
        else:
            persistent_notification.async_dismiss(self.hass, "onstar_cn_cmd")
