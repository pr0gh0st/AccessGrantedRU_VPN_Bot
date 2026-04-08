from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import User, async_session_factory, get_active_users_subscription_ending_within
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
    Один проход: напоминание за 24 часа и за 1 час до subscription_end.
    Дедупликация по полям reminder_*_for_subscription_end == текущий subscription_end.
    """

    async with async_session_factory() as session:
        users = await get_active_users_subscription_ending_within(
            session,
            now=now,
            within_hours=48,
            limit=5000,
        )

        for user in users:
            await _maybe_notify_user(session, bot, user, now)


async def _maybe_notify_user(session: AsyncSession, bot: Bot, user: User, now: dt.datetime) -> None:
    if user.subscription_end is None:
        return

    rem = _remaining(user.subscription_end, now)
    if rem <= dt.timedelta(0):
        return

    sub_end = user.subscription_end

    # Сначала более срочное (≤1 ч), затем 24 ч.
    if dt.timedelta(0) < rem <= dt.timedelta(hours=1):
        if _same_subscription_end(user.reminder_1h_for_subscription_end, sub_end):
            return
        text = (
            "Напоминание: до окончания подписки осталось менее часа.\n"
            f"Окончание: {format_datetime_ru(sub_end)}"
        )
        if await _send_and_mark(
            session,
            bot,
            user,
            text,
            mark_24h=False,
            mark_1h=True,
        ):
            logger.info("Sent 1h reminder tg_id=%s", user.telegram_id)
        return

    if dt.timedelta(hours=1) < rem <= dt.timedelta(hours=24):
        if _same_subscription_end(user.reminder_24h_for_subscription_end, sub_end):
            return
        text = (
            "Напоминание: до окончания подписки осталось менее 24 часов.\n"
            f"Окончание: {format_datetime_ru(sub_end)}"
        )
        if await _send_and_mark(
            session,
            bot,
            user,
            text,
            mark_24h=True,
            mark_1h=False,
        ):
            logger.info("Sent 24h reminder tg_id=%s", user.telegram_id)


async def _send_and_mark(
    session: AsyncSession,
    bot: Bot,
    user: User,
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

    sub = user.subscription_end
    if mark_24h:
        user.reminder_24h_for_subscription_end = sub
    if mark_1h:
        user.reminder_1h_for_subscription_end = sub
    await session.commit()
    return True
