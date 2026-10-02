"""安吉星(中国) API 客户端 —— 逆向自安吉星微信小程序。

加密: AES-128-CBC, key=iv="360fe65ae392fec2", base64(PKCS7)
刷新: POST /sos/miniapp/v1/oauth/refresh {permToken, username}
指令: POST /sos/vehoa/v2/remote/control {type, vin, requestChannel}
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import aiohttp
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

from .const import (
    AES_KEY, BASE, CLIENT_INFO, CLIENT_VERSION, TOKEN_MARGIN,
)

_LOGGER = logging.getLogger(__name__)


class OnStarError(Exception):
    """安吉星接口错误。"""


class OnStarAuthError(OnStarError):
    """凭据/令牌失效，需要重新提供 perm_token。"""


def encrypt_body(plaintext: str) -> str:
    """与小程序 utils/encryption.js encryptBody 一致。"""
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_KEY))
    enc = cipher.encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


class OnStarApi:
    def __init__(self, session: aiohttp.ClientSession, username: str,
                 perm_token: str, vin: str) -> None:
        self._session = session
        self.username = username
        self.perm_token = perm_token
        self.vin = vin
        self.access_token: str | None = None
        self.expires_at: float = 0.0
        self.expires_in: int = 0
        # 最近一次指令结果: {"cmd","status","message","time"}
        self.last_result: dict | None = None

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
        if extra:
            headers.update(extra)
        async with self._session.post(
            BASE + path, headers=headers,
            data=json.dumps(body) if body is not None else "",
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            try:
                return json.loads(text)
            except ValueError as err:
                raise OnStarError(f"非 JSON 响应 ({resp.status}): {text[:200]}") from err

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

    # ---------- 远程指令 ----------
    async def async_control(self, cmd: str) -> str:
        await self.async_ensure_token()
        d = await self._post(
            "/sos/vehoa/v2/remote/control",
            {"type": cmd, "vin": self.vin, "requestChannel": "legacy"},
            {"client-user-id": self.username, "channel": "SOSWMP"},
        )
        if d.get("bizCode") != "E0000":
            raise OnStarError(f"指令 {cmd} 失败: {d.get('bizCode')} {d.get('bizMsg')}")
        return d["data"]["requestId"]

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
        import datetime as _dt
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
        """把诊断结果解析成 {name: {value, unit}}。"""
        out: dict = {}
        try:
            elems = res["body"]["diagnosticResponse"][0]["diagnosticElement"]
        except (KeyError, IndexError, TypeError):
            return out
        for el in elems:
            name = el.get("name")
            if not name:
                continue
            out[name] = {"value": el.get("value"), "unit": el.get("unit", "")}
        return out
