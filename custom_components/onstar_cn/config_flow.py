"""配置流程：首次配置 / 重新认证 / 修改。"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OnStarApi, OnStarAuthError, OnStarError, OnStarPinError
from .const import CONF_PERM_TOKEN, CONF_PIN, CONF_USERNAME, CONF_VIN, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PERM_TOKEN): str,
        vol.Required(CONF_VIN): str,
        vol.Optional(CONF_PIN, default=""): str,
    }
)
STEP_TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_PERM_TOKEN): str})


class OnStarConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, username: str, perm_token: str, vin: str,
                     pin: str = "") -> str | None:
        """校验凭据；返回错误 key 或 None。"""
        api = OnStarApi(
            async_get_clientsession(self.hass),
            username=username, perm_token=perm_token, vin=vin, pin=pin,
        )
        try:
            await api.async_refresh()
        except OnStarAuthError:
            return "invalid_auth"
        except OnStarError:
            return "invalid_auth"
        except Exception:  # noqa: BLE001
            return "cannot_connect"
        # 填了服务密码就顺手校验一下，避免装好了才发现写操作不能用
        if pin:
            try:
                await api.async_verify_pin()
            except OnStarPinError:
                return "invalid_pin"
            except Exception:  # noqa: BLE001
                return "cannot_connect"
        return None

    # ---------- 首次配置 ----------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            vin = user_input[CONF_VIN].strip().upper()
            pin = (user_input.get(CONF_PIN) or "").strip()
            await self.async_set_unique_id(vin)
            self._abort_if_unique_id_configured()

            err = await self._check(username, user_input[CONF_PERM_TOKEN].strip(),
                                    vin, pin)
            if err:
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=f"安吉星 {vin[-6:]}",
                    data={
                        CONF_USERNAME: username,
                        CONF_PERM_TOKEN: user_input[CONF_PERM_TOKEN].strip(),
                        CONF_VIN: vin,
                        CONF_PIN: pin,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    # ---------- 修改（入口已存在）----------
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            vin = user_input[CONF_VIN].strip().upper()
            pin = (user_input.get(CONF_PIN) or "").strip()
            err = await self._check(username, user_input[CONF_PERM_TOKEN].strip(),
                                    vin, pin)
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PERM_TOKEN: user_input[CONF_PERM_TOKEN].strip(),
                        CONF_VIN: vin,
                        CONF_PIN: pin,
                    },
                )
        else:
            user_input = {
                CONF_USERNAME: entry.data[CONF_USERNAME],
                CONF_VIN: entry.data[CONF_VIN],
                CONF_PIN: entry.data.get(CONF_PIN, ""),
                CONF_PERM_TOKEN: "",
            }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    # ---------- 重新认证（令牌失效时自动弹出）----------
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            err = await self._check(
                entry.data[CONF_USERNAME],
                user_input[CONF_PERM_TOKEN].strip(),
                entry.data[CONF_VIN],
            )
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PERM_TOKEN: user_input[CONF_PERM_TOKEN].strip()},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={"vin": entry.data[CONF_VIN]},
        )
