"""远程控制按钮。"""
from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OnStarApi, OnStarError
from .const import (
    CMD_CANCEL_FLASH, CMD_CANCEL_START, CMD_FLASH, CMD_START, DOMAIN, EVENT_COMMAND,
)
from .entity import build_device_info

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
    data = hass.data[DOMAIN][entry.entry_id]
    api: OnStarApi = data["api"]
    vehicle = data.get("vehicle")
    async_add_entities(
        OnStarButton(hass, api, entry, vehicle, key, name, cmd)
        for key, name, cmd in BUTTONS
    )


class OnStarButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, api: OnStarApi, entry: ConfigEntry,
                 vehicle: dict | None, key: str, name: str, cmd: str) -> None:
        self.hass = hass
        self._api = api
        self._cmd = cmd
        self._attr_name = name
        self._attr_unique_id = f"{entry.data['vin']}_{key}"
        self._attr_device_info = build_device_info(entry.data["vin"], vehicle)

    async def async_press(self) -> None:
        _LOGGER.debug("按下 %s -> %s", self.name, self._cmd)
        try:
            await self._api.async_run(self._cmd)
        except OnStarError as err:
            self._report(ok=False, res=self._api.last_result or {})
            raise HomeAssistantError(f"安吉星「{self.name}」失败：{err}") from err
        self._report(ok=True, res=self._api.last_result or {})

    def _report(self, ok: bool, res: dict) -> None:
        self.hass.bus.async_fire(EVENT_COMMAND, {
            "name": self.name, "cmd": self._cmd,
            "success": ok, "status": res.get("status"),
            "message": res.get("message"),
        })
        if ok:
            persistent_notification.async_dismiss(self.hass, "onstar_cn_cmd")
            return
        msg = res.get("message") or "未知错误"
        title = "需要服务密码" if "服务密码" in msg else "安吉星指令失败"
        persistent_notification.async_create(
            self.hass,
            f"「{self.name}」执行失败\n状态：{res.get('status')}\n信息：{msg}",
            title=title, notification_id="onstar_cn_cmd",
        )
