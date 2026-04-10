from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import delete

from .config import settings
from .database import (
    UserVlessKey,
    async_session_factory,
    get_user_by_id,
    init_db,
    list_user_vless_keys,
    list_vless_keys_expired,
    sync_user_legacy_vless_from_keys,
    sync_user_subscription_aggregate,
)
from .functions import XUIAPI
from .handlers import router
from .reminders import run_subscription_reminder_tick

logger = logging.getLogger(__name__)


async def _expired_subscriptions_worker(bot: Bot) -> None:
    """
    Hourly background task:
    - находим ключи с истекшим subscription_end;
    - удаляем клиента в XUI и строку ключа;
    - синхронизируем сводку по пользователю;
    - уведомляем (если у пользователя ещё есть другие ключи — только про этот ключ).
    """

    while True:
        try:
            async with async_session_factory() as session:
                expired_keys = await list_vless_keys_expired(session, limit=500)

                if expired_keys:
                    xui = XUIAPI()
                    try:
                        for key in expired_keys:
                            user = await get_user_by_id(session, user_id=key.user_id)
                            if user is None:
                                continue

                            keys_before = await list_user_vless_keys(session, user_id=user.id)
                            display_num = next(
                                (i + 1 for i, k in enumerate(keys_before) if k.id == key.id),
                                0,
                            )

                            try:
                                await xui.remove_client(
                                    inbound_id=settings.INBOUND_ID, client_id=key.vless_uuid
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to remove expired key client in XUI tg_id=%s key_id=%s",
                                    user.telegram_id,
                                    key.id,
                                    exc_info=True,
                                )

                            await session.execute(delete(UserVlessKey).where(UserVlessKey.id == key.id))
                            await session.commit()
                            await sync_user_legacy_vless_from_keys(session, user_id=user.id)
                            await sync_user_subscription_aggregate(session, user_id=user.id)

                            remaining = await list_user_vless_keys(session, user_id=user.id)
                            try:
                                if remaining:
                                    await bot.send_message(
                                        chat_id=user.telegram_id,
                                        text=(
                                            f"Срок действия ключа №{display_num} истёк, он отключён.\n"
                                            "Остальные ключи (если есть) продолжают работать до своей даты."
                                        ),
                                    )
                                else:
                                    await bot.send_message(
                                        chat_id=user.telegram_id,
                                        text=(
                                            "Срок действия всех VPN-ключей истёк.\n"
                                            "Чтобы продолжить пользоваться сервисом, продлите доступ в разделе «Купить подписку»."
                                        ),
                                    )
                            except TelegramAPIError:
                                logger.info("Cannot notify expired key user tg_id=%s", user.telegram_id)
                    finally:
                        await xui.close()
        except Exception:
            logger.exception("Expired subscriptions worker iteration failed")

        await asyncio.sleep(3600)


async def _subscription_reminders_worker(bot: Bot) -> None:
    """Каждые 5 минут: напоминания за 24 ч и за 1 ч до окончания подписки."""

    while True:
        try:
            await run_subscription_reminder_tick(bot, now=dt.datetime.now(tz=dt.timezone.utc))
        except Exception:
            logger.exception("Subscription reminders worker iteration failed")

        await asyncio.sleep(300)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Fail fast on missing critical env vars.
    settings.validate_required()

    await init_db()

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    worker_task = asyncio.create_task(_expired_subscriptions_worker(bot))
    reminders_task = asyncio.create_task(_subscription_reminders_worker(bot))
    try:
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        reminders_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        with contextlib.suppress(asyncio.CancelledError):
            await reminders_task


if __name__ == "__main__":
    asyncio.run(main())

