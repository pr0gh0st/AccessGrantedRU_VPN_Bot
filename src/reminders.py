from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import User, UserVlessKey, async_session_factory, get_vless_keys_subscription_ending_within
from .utils import format_datetime_ru

logger = logging.getLogger(__name__)


def _utc_normalize(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _same_subscription_end(a: Optional[dt.datetime], b: Optional[dt.datetime]) -> bool:
    """Совпадение даты окончания текущего периода (с допуском по секундам)."""
    if a is None or b is None:
        return False
    na, nb = _utc_normalize(a), _utc_normalize(b)
    return abs((na - nb).total_seconds()) < 2.0


def _remaining(subscription_end: dt.datetime, now: dt.datetime) -> dt.timedelta:
    end = _utc_normalize(subscription_end)
    n = _utc_normalize(now)
    assert end is not None and n is not None
    return end - n


async def run_subscription_reminder_tick(bot: Bot, *, now: dt.datetime) -> None:
    """
    Один проход: напоминание за 24 ч и за 1 ч до окончания срока каждого ключа.
    Дедупликация по полям reminder_* на строке user_vless_keys.
    """

    async with async_session_factory() as session:
        pairs = await get_vless_keys_subscription_ending_within(
            session,
            now=now,
            within_hours=48,
            limit=5000,
        )

        for user, key in pairs:
            await _maybe_notify_for_key(session, bot, user, key, now)


async def _key_display_number(session: AsyncSession, *, user_id: int, key_id: int) -> int:
    from .database import list_user_vless_keys

    keys = await list_user_vless_keys(session, user_id=user_id)
    for i, k in enumerate(keys):
        if k.id == key_id:
            return i + 1
    return key_id


async def _maybe_notify_for_key(
    session: AsyncSession,
    bot: Bot,
    user: User,
    key: UserVlessKey,
    now: dt.datetime,
) -> None:
    if key.subscription_end is None:
        return

    rem = _remaining(key.subscription_end, now)
    if rem <= dt.timedelta(0):
        return

    sub_end = key.subscription_end
    num = await _key_display_number(session, user_id=user.id, key_id=key.id)

    if dt.timedelta(0) < rem <= dt.timedelta(hours=1):
        if _same_subscription_end(key.reminder_1h_for_subscription_end, sub_end):
            return
        text = (
            f"Напоминание: до окончания срока ключа №{num} осталось менее часа.\n"
            f"Окончание: {format_datetime_ru(sub_end)}"
        )
        if await _send_and_mark_key(
            session,
            bot,
            user,
            key,
            text,
            mark_24h=False,
            mark_1h=True,
        ):
            logger.info("Sent 1h key reminder tg_id=%s key_id=%s", user.telegram_id, key.id)
        return

    if dt.timedelta(hours=1) < rem <= dt.timedelta(hours=24):
        if _same_subscription_end(key.reminder_24h_for_subscription_end, sub_end):
            return
        text = (
            f"Напоминание: до окончания срока ключа №{num} осталось менее 24 часов.\n"
            f"Окончание: {format_datetime_ru(sub_end)}"
        )
        if await _send_and_mark_key(
            session,
            bot,
            user,
            key,
            text,
            mark_24h=True,
            mark_1h=False,
        ):
            logger.info("Sent 24h key reminder tg_id=%s key_id=%s", user.telegram_id, key.id)


async def _send_and_mark_key(
    session: AsyncSession,
    bot: Bot,
    user: User,
    key: UserVlessKey,
    text: str,
    *,
    mark_24h: bool,
    mark_1h: bool,
) -> bool:
    try:
        await bot.send_message(chat_id=user.telegram_id, text=text)
    except TelegramAPIError:
        logger.info("Cannot send reminder to tg_id=%s", user.telegram_id)
        return False

    sub = key.subscription_end
    if mark_24h:
        key.reminder_24h_for_subscription_end = sub
    if mark_1h:
        key.reminder_1h_for_subscription_end = sub
    await session.commit()
    return True
