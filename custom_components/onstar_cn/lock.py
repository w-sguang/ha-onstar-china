"""车门锁实体。"""
from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OnStarApi, OnStarError
from .const import CMD_LOCK, CMD_UNLOCK, DOMAIN, EVENT_COMMAND
from .entity import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [OnStarLock(hass, data["api"], entry, data.get("vehicle"))]
    )


class OnStarLock(LockEntity):
    _attr_has_entity_name = True
    _attr_name = "车门锁"
    _attr_assumed_state = True

    def __init__(self, hass: HomeAssistant, api: OnStarApi, entry: ConfigEntry,
                 vehicle: dict | None = None) -> None:
        self.hass = hass
        self._api = api
        self._attr_unique_id = f"{entry.data['vin']}_lock"
        self._attr_device_info = build_device_info(entry.data["vin"], vehicle)

    async def _do(self, cmd: str, locked: bool) -> None:
        name = "上锁" if locked else "解锁"
        try:
            await self._api.async_run(cmd)
        except OnStarError as err:
            self._report(name, ok=False, res=self._api.last_result or {})
            raise HomeAssistantError(f"安吉星{name}失败：{err}") from err
        self._report(name, ok=True, res=self._api.last_result or {})
        self._attr_is_locked = locked
        self.async_write_ha_state()

    async def async_lock(self, **kwargs) -> None:
        await self._do(CMD_LOCK, True)

    async def async_unlock(self, **kwargs) -> None:
        await self._do(CMD_UNLOCK, False)

    def _report(self, name: str, ok: bool, res: dict) -> None:
        self.hass.bus.async_fire(EVENT_COMMAND, {
            "name": name, "cmd": res.get("cmd"), "success": ok,
            "status": res.get("status"), "message": res.get("message"),
        })
        if ok:
            persistent_notification.async_dismiss(self.hass, "onstar_cn_cmd")
            return
        msg = res.get("message") or "未知错误"
        if "服务密码" in msg:
            title = "需要服务密码"
        else:
            title = "安吉星指令失败"
        persistent_notification.async_create(
            self.hass,
            f"「{name}」执行失败\n状态：{res.get('status')}\n信息：{msg}",
            title=title, notification_id="onstar_cn_cmd",
        )
