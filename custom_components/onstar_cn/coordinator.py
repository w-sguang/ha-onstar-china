"""数据协调器：轮询车况。"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OnStarApi, OnStarAuthError, OnStarError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class OnStarCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: OnStarApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            res = await self.api.async_diagnostics()
        except OnStarAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OnStarError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"车况获取失败: {err}") from err
        return self.api.parse_diagnostics(res)
