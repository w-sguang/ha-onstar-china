"""车门锁实体。"""
from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OnStarApi
from .const import CMD_LOCK, CMD_UNLOCK, DOMAIN, EVENT_COMMAND

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OnStarLock(hass, data["api"], entry)])


class OnStarLock(LockEntity):
    _attr_has_entity_name = True
    _attr_name = "车门锁"
    _attr_assumed_state = True

    def __init__(self, hass: HomeAssistant, api: OnStarApi, entry: ConfigEntry) -> None:
        self.hass = hass
        self._api = api
        self._attr_unique_id = f"{entry.data['vin']}_lock"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["vin"])},
            "name": f"安吉星 {entry.data['vin'][-6:]}",
            "manufacturer": "OnStar China",
            "model": "上汽通用 OnStar 车辆",
        }

    async def _do(self, cmd: str, locked: bool) -> None:
        await self._api.async_run(cmd)
        self._report("上锁" if locked else "解锁")
        self._attr_is_locked = locked
        self.async_write_ha_state()

    async def async_lock(self, **kwargs) -> None:
        await self._do(CMD_LOCK, True)

    async def async_unlock(self, **kwargs) -> None:
        await self._do(CMD_UNLOCK, False)

    def _report(self, name: str) -> None:
        res = self._api.last_result or {}
        status = str(res.get("status", "unknown")).lower()
        ok = status in ("success", "succeeded")
        self.hass.bus.async_fire(EVENT_COMMAND, {
            "name": name, "cmd": res.get("cmd"), "success": ok,
            "status": res.get("status"), "message": res.get("message"),
        })
        if ok:
            persistent_notification.async_dismiss(self.hass, "onstar_cn_cmd")
        else:
            persistent_notification.async_create(
                self.hass,
                f"「{name}」执行失败\n状态：{res.get('status')}\n信息：{res.get('message') or '无'}",
                title="安吉星指令失败", notification_id="onstar_cn_cmd")
