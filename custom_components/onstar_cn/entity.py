"""共用实体工具：根据车辆信息构造 device_info。"""
from __future__ import annotations

from .const import DOMAIN


def vehicle_display(vehicle: dict | None) -> tuple[str, str]:
    """返回 (品牌, 车型+年款)。"""
    v = vehicle or {}
    model_desc = (v.get("modelDesc") or "").strip()
    year = (v.get("year") or "").strip()
    brand = model_desc.split()[0] if model_desc else ""
    if not brand:
        brand = (v.get("brand") or "").strip()
    model = " ".join(x for x in (model_desc, year) if x)
    return brand, model


def build_device_info(vin: str, vehicle: dict | None) -> dict:
    """构造与车辆信息一致的 device_info。

    所有实体必须共用同一份，否则 HA 会把同一设备拆成多个。
    """
    v = vehicle or {}
    manufacturer = (v.get("makeDesc") or "上汽通用").strip() or "上汽通用"
    _, model = vehicle_display(v)
    info = {
        "identifiers": {(DOMAIN, vin)},
        # 设备名保持稳定，避免改名导致 entity_id 变化（会破坏用户的自动化）
        "name": f"安吉星 {vin[-6:]}",
        "manufacturer": manufacturer,
        "serial_number": vin,
        "model": model or "上汽通用 OnStar 车辆",
    }
    generation = (v.get("generationDescription") or "").strip()
    if generation:
        info["hw_version"] = generation
    return info
