from __future__ import annotations

import datetime as dt
from typing import Optional
from zoneinfo import ZoneInfo

_MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def format_bytes_gb(value_bytes: int) -> str:
    """
    Format bytes as GB for user-friendly output.

    Uses 1024^3 (GiB-like) to match most VPN/tunnel dashboards.
    """

    value_bytes = max(0, int(value_bytes))
    gb = value_bytes / (1024**3)
    return f"{gb:.2f} ГБ"


def format_datetime_ru(value: Optional[dt.datetime]) -> str:
    if value is None:
        return "не задано"
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    local = value.astimezone(_MOSCOW_TZ)
    return local.strftime("%Y-%m-%d %H:%M МСК")


def truncate_payload(text: str, *, max_len: int = 512) -> str:
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

