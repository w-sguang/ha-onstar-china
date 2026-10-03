"""安吉星(中国) 集成入口。"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OnStarApi, OnStarAuthError
from .const import CONF_PERM_TOKEN, CONF_PIN, CONF_USERNAME, CONF_VIN, DOMAIN
from .coordinator import OnStarCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["lock", "button", "sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = OnStarApi(
        session,
        username=entry.data[CONF_USERNAME],
        perm_token=entry.data[CONF_PERM_TOKEN],
        vin=entry.data[CONF_VIN],
        pin=entry.data.get(CONF_PIN),
    )
    coordinator = OnStarCoordinator(hass, api)
    try:
        await api.async_refresh()
    except OnStarAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err

    # 车辆品牌/车型/年款（非关键，失败也不影响集成）
    vehicle: dict = {}
    try:
        vehicle = await api.async_vehicle_info()
        _LOGGER.debug("车辆信息: %s", vehicle)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("获取车辆品牌/型号失败（不影响使用）: %s", err)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "vehicle": vehicle,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
