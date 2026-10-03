"""安吉星(中国) API 客户端 —— 逆向自安吉星微信小程序。

加密: AES-128-CBC, key=iv="360fe65ae392fec2", base64(PKCS7)
刷新: POST /sos/miniapp/v1/oauth/refresh {permToken, username}
指令: POST /sos/vehoa/v2/remote/control {type, vin, requestChannel}
写操作(锁车/解锁/启动/鸣笛)需先校验服务密码:
      POST /sos/personoa/v1/pin/verifyPin {pin, vin}  —— 服务端下发会话 cookie，
      后续指令必须带上同一 cookie，否则报 E7011。
"""
from __future__ import annotations

import asyncio
import base64
import datetime as _dt
import json
import logging
import time

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    AES_KEY,
    BASE,
    CLIENT_INFO,
    CLIENT_VERSION,
    CMDS_NEED_PIN,
    PIN_TTL,
    TOKEN_MARGIN,
)

_LOGGER = logging.getLogger(__name__)


class OnStarError(Exception):
    """安吉星接口错误。"""


class OnStarAuthError(OnStarError):
    """凭据/令牌失效，需要重新提供 perm_token。"""


class OnStarPinError(OnStarError):
    """服务密码(PIN)缺失或校验失败。"""


def encrypt_body(plaintext: str) -> str:
    """与小程序 utils/encryption.js encryptBody 一致。"""
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_KEY))
    enc = cipher.encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


class OnStarApi:
    def __init__(self, session: aiohttp.ClientSession, username: str,
                 perm_token: str, vin: str, pin: str | None = None) -> None:
        self._session = session
        self.username = username
        self.perm_token = perm_token
        self.vin = vin
        self.pin = (pin or "").strip() or None
        self.access_token: str | None = None
        self.expires_at: float = 0.0
        self.expires_in: int = 0
        # 最近一次指令结果: {"cmd","status","message","time"}
        self.last_result: dict | None = None
        # PIN 校验会话
        self._pin_verified_at: float = 0.0
        self._cookies: dict[str, str] = {}

    # ---------- 底层 ----------
    async def _post(self, path: str, body: dict | None, extra: dict | None = None,
                    auth: bool = True) -> dict:
        headers = {
            "CLIENT-INFO": CLIENT_INFO,
            "CLIENT-VERSION": CLIENT_VERSION,
            "Content-Type": "application/json",
        }
        if auth and self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        if extra:
            headers.update(extra)
        async with self._session.post(
            BASE + path, headers=headers,
            data=json.dumps(body) if body is not None else "",
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            # 服务端的会话 cookie 必须留存，写指令时回传
            for k, v in resp.cookies.items():
                self._cookies[k] = v.value
            text = await resp.text()
            try:
                return json.loads(text)
            except ValueError as err:
                raise OnStarError(f"非 JSON 响应 ({resp.status}): {text[:200]}") from err

    async def _get(self, path: str, extra: dict | None = None,
                   auth: bool = True) -> dict:
        headers = {
            "CLIENT-INFO": CLIENT_INFO,
            "CLIENT-VERSION": CLIENT_VERSION,
        }
        if auth and self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        if extra:
            headers.update(extra)
        async with self._session.get(
            BASE + path, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            for k, v in resp.cookies.items():
                self._cookies[k] = v.value
            text = await resp.text()
            try:
                return json.loads(text)
            except ValueError as err:
                raise OnStarError(f"非 JSON 响应 ({resp.status}): {text[:200]}") from err

    # ---------- 车辆信息（品牌/车型/年款） ----------
    async def async_vehicle_info(self) -> dict:
        """GET /sos/mobileaggr/v1/user/<idpUserId>/suite → currentSuite.vehicle。

        含 modelDesc(别克 君威)、year(2023)、brand(BUICK)、makeDesc(上汽通用) 等。
        """
        await self.async_ensure_token()
        d = await self._get(f"/sos/mobileaggr/v1/user/{self.username}/suite")
        suite = d.get("currentSuite") or {}
        return suite.get("vehicle") or {}

    # ---------- token ----------
    async def async_refresh(self) -> None:
        d = await self._post(
            "/sos/miniapp/v1/oauth/refresh",
            {"permToken": self.perm_token, "username": self.username},
            auth=False,
        )
        if d.get("bizCode") != "E0000":
            raise OnStarAuthError(
                f"token 刷新失败: {d.get('bizCode')} {d.get('bizMsg')}")
        biz = d.get("bizData") or {}
        if str(biz.get("statusCode")) not in ("200", "None") and biz.get("message"):
            # 例如 C401_1 Invalid Refresh Token
            raise OnStarAuthError(
                f"token 刷新失败: {biz.get('subStatusCode') or biz.get('statusCode')} "
                f"{biz.get('message')}")
        inner = biz["data"]
        self.access_token = inner["access_token"]
        # 若服务端轮换 perm_token，则保存新的（防御性）
        if inner.get("perm_token"):
            self.perm_token = inner["perm_token"]
        self.expires_in = int(inner.get("expires_in", 1800000)) // 1000
        self.expires_at = time.time() + self.expires_in
        _LOGGER.debug("onstar token 刷新成功, 有效期 %ss", self.expires_in)

    async def async_ensure_token(self) -> None:
        if not self.access_token or time.time() > self.expires_at - TOKEN_MARGIN:
            await self.async_refresh()

    # ---------- 服务密码(PIN) ----------
    @property
    def pin_configured(self) -> bool:
        return self.pin is not None

    async def async_verify_pin(self) -> None:
        """校验服务密码，并保留服务端下发的会话 cookie。"""
        if not self.pin:
            raise OnStarPinError(
                "未配置服务密码。安吉星对锁车/解锁/远程启动等**写操作**要求校验服务密码："
                "请在「设置 → 设备与服务 → 安吉星 → 配置」里填写后重试。")
        await self.async_ensure_token()
        d = await self._post(
            "/sos/personoa/v1/pin/verifyPin",
            {"pin": self.pin, "vin": self.vin},
            {"client-user-id": self.username, "channel": "SOSWMP"},
        )
        if d.get("bizCode") != "E0000":
            raise OnStarPinError(
                f"服务密码校验失败：{d.get('bizMsg') or d.get('bizCode')}（请确认配置里的服务密码是否正确）")
        self._pin_verified_at = time.time()

    def _pin_fresh(self) -> bool:
        return bool(self._pin_verified_at) and (
            time.time() - self._pin_verified_at < PIN_TTL)

    # ---------- 远程指令 ----------
    async def async_control(self, cmd: str) -> str:
        await self.async_ensure_token()
        need_pin = cmd in CMDS_NEED_PIN
        last_msg = ""
        for attempt in (1, 2):
            if need_pin and (attempt == 2 or not self._pin_fresh()):
                await self.async_verify_pin()
            d = await self._post(
                "/sos/vehoa/v2/remote/control",
                {"type": cmd, "vin": self.vin, "requestChannel": "legacy"},
                {"client-user-id": self.username, "channel": "SOSWMP"},
            )
            code = d.get("bizCode")
            if code == "E0000":
                return d["data"]["requestId"]
            last_msg = f"{code} {d.get('bizMsg')}"
            # E7011 = 需验证 PIN：重新校验一次后再试（最多重试一次）
            if need_pin and code == "E7011" and attempt == 1:
                _LOGGER.debug("收到 E7011，重新校验服务密码后重试")
                self._pin_verified_at = 0.0
                continue
            if code == "E7011":
                raise OnStarPinError(
                    f"指令被拒绝（{last_msg}）：服务密码校验未通过，请在集成配置里检查服务密码。")
            raise OnStarError(f"指令 {cmd} 失败: {last_msg}")
        raise OnStarError(f"指令 {cmd} 失败: {last_msg}")

    async def async_result(self, request_id: str) -> dict:
        await self.async_ensure_token()
        d = await self._post(
            "/sos/vehoa/v2/remote/result",
            {"requestChannel": "legacy", "vin": self.vin, "requestId": request_id},
            {"client-user-id": self.username, "channel": "SOSWMP"},
        )
        return (d.get("data") or {}).get("commandResponse") or {}

    async def async_run(self, cmd: str, timeout: int = 120, interval: int = 3) -> dict:
        """下发指令并轮询结果。结果写入 self.last_result。"""
        try:
            rid = await self.async_control(cmd)
        except OnStarError as err:
            self.last_result = {
                "cmd": cmd, "status": "failed", "message": str(err),
                "time": _dt.datetime.now().isoformat(timespec="seconds"),
            }
            raise
        deadline = time.time() + timeout
        last: dict = {}
        while time.time() < deadline:
            res = await self.async_result(rid)
            if res:
                last = res
                status = (res.get("status") or "").lower()
                if status and status not in ("inprogress", "in_progress",
                                             "pending", "request_success"):
                    self.last_result = {
                        "cmd": cmd,
                        "status": res.get("status"),
                        "message": res.get("errorMessage") or res.get("message") or "",
                        "time": _dt.datetime.now().isoformat(timespec="seconds"),
                    }
                    return res
            await asyncio.sleep(interval)
        last = last or {"status": "timeout"}
        self.last_result = {
            "cmd": cmd, "status": last.get("status", "timeout"),
            "message": "等待结果超时", "time": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        return last

    # ---------- 只读车况 ----------
    async def async_diagnostics(self) -> dict:
        await self.async_ensure_token()
        d = await self._post(
            "/sos/vehoa/v1/remote/result/lastDiagnostics",
            {"vin": self.vin},
            {"client-user-id": self.username, "user-token": self.username,
             "channel": "SOSWMP"},
        )
        return (d.get("data") or {}).get("commandResponse") or {}

    @staticmethod
    def parse_diagnostics(res: dict) -> dict:
        """把诊断结果解析成 {name: {value, unit, message}}（_meta 为数据时间）。"""
        out: dict = {}
        body = (res or {}).get("body") or {}
        groups = body.get("diagnosticResponse") or []
        if isinstance(groups, dict):
            groups = [groups]
        for grp in groups:
            for el in (grp or {}).get("diagnosticElement") or []:
                name = el.get("name")
                if not name:
                    continue
                out[name] = {
                    "value": el.get("value"),
                    "unit": el.get("unit", ""),
                    "message": el.get("message", ""),
                }
        out["_meta"] = {
            "updated": (res or {}).get("completionTime"),
            "requested": (res or {}).get("requestTime"),
        }
        return out
