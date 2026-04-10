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
    get_expired_active_users,
    init_db,
    list_user_vless_keys,
)
from .functions import XUIAPI
from .handlers import router
from .reminders import run_subscription_reminder_tick

logger = logging.getLogger(__name__)


async def _expired_subscriptions_worker(bot: Bot) -> None:
    """
    Hourly background task:
    - find expired active users
    - remove VLESS client from XUI
    - deactivate user in DB
    - notify user
    """

    while True:
        try:
            async with async_session_factory() as session:
                expired_users = await get_expired_active_users(session, limit=500)

                if expired_users:
                    xui = XUIAPI()
                    try:
                        for user in expired_users:
                            keys = await list_user_vless_keys(session, user_id=user.id)
                            for k in keys:
                                try:
                                    await xui.remove_client(
                                        inbound_id=settings.INBOUND_ID, client_id=k.vless_uuid
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed to remove expired user client in XUI tg_id=%s",
                                        user.telegram_id,
                                    )

                            await session.execute(delete(UserVlessKey).where(UserVlessKey.user_id == user.id))
                            user.is_active = False
                            user.vless_uuid = None
                            user.vless_email = None
                            user.vless_remark = None
                            user.vless_profile_data = None
                            await session.commit()

                            try:
                                await bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=(
                                        "Срок вашей подписки истёк.\n"
                                        "VPN-ключи отключены. Чтобы продолжить пользоваться сервисом, продлите подписку."
                                    ),
                                )
                            except TelegramAPIError:
                                logger.info("Cannot notify expired user tg_id=%s", user.telegram_id)
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

