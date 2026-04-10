from __future__ import annotations

import datetime as dt
import html as html_module
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


def format_price_minor(amount: int, currency: str) -> str:
    """
    Человекочитаемая цена из минорных единиц валюты (как в Telegram Payments).

    RUB — копейки (30000 → «300 ₽»), USD/EUR — центы.
    """

    c = (currency or "").strip().upper() or "USD"
    amount = max(0, int(amount))
    if c == "RUB":
        rub = amount // 100
        kop = amount % 100
        if kop:
            return f"{rub},{kop:02d} ₽"
        return f"{rub} ₽"
    if c in ("USD", "EUR"):
        return f"{amount / 100:.2f} {c}"
    return f"{amount} {c}"


def vless_url_as_html_code(vless_url: str) -> str:
    """Telegram HTML: VLESS-ссылка в моноширинном блоке для удобного копирования."""

    return f"<code>{html_module.escape(vless_url)}</code>"


def trial_extra_deadline_phrase_ru(minutes: int) -> str:
    """Фраза «в течение …» для срока бесплатного доп. ключа."""

    m = max(1, int(minutes))
    if m == 60:
        return "в течение часа"
    return f"в течение {m} минут"


def truncate_payload(text: str, *, max_len: int = 512) -> str:
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

