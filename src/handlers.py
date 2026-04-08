from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .config import settings
from .database import async_session_factory
from .database import reset_trial_for_user
from .functions import XUIAPI
from .admin_handlers import admin_router
from .client_guide import GUIDE_TEXT_BY_PLATFORM, RU_ROUTING_HAPP_IMPORT
from .keyboards import (
    admin_main_inline_kb,
    confirm_delete_vpn_inline_kb,
    help_inline_kb,
    main_menu_inline_kb,
    profile_inline_kb,
    trial_inline_kb,
    vpn_inline_kb,
    vless_connection_help_kb,
)
from .services import (
    ServiceError,
    activate_trial_and_create_vless_profile,
    delete_vless_profile_for_user,
    ensure_vless_profile_for_user,
    fetch_and_update_traffic_for_user,
    get_or_create_user,
    user_can_activate_trial,
    _is_subscription_active,
)
from .utils import format_bytes_gb, format_datetime_ru

logger = logging.getLogger(__name__)

router = Router(name="bot_router")
router.include_router(admin_router)


def _now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _profile_status_text(user: Any) -> str:
    subscription_active = _is_subscription_active(user)
    return (
        "Ваш профиль\n"
        f"ID: {user.telegram_id}\n"
        f"Пробный период использован: {'да' if user.is_trial_used else 'нет'}\n"
        f"Подписка активна: {'да' if subscription_active else 'нет'}\n"
        f"Окончание подписки: {format_datetime_ru(user.subscription_end)}"
    )


def _myvpn_status_text(user: Any) -> str:
    subscription_active = _is_subscription_active(user)
    has_vless = bool(user.vless_uuid and user.vless_remark)
    return (
        "Мой VPN\n"
        f"Подписка активна: {'да' if subscription_active else 'нет'}\n"
        f"VLESS профиль: {'есть' if has_vless else 'нет'}"
    )


async def _get_user_for_message(session, tg_user) -> Any:
    return await get_or_create_user(
        session=session,
        telegram_id=tg_user.id,
        username=tg_user.username,
        full_name=(tg_user.full_name if tg_user else None),
    )


def _is_admin_user(user: Any) -> bool:
    return bool(user.is_admin or (user.telegram_id in settings.admin_ids))


async def _send_vless_connection_help(message: Message) -> None:
    await message.answer(
        "Теперь Вы можете скопировать ссылку в Ваше приложение\n\n"
        "Выберите платформу для инструкции:",
        reply_markup=vless_connection_help_kb(),
    )


async def _with_xui():
    xui = XUIAPI()
    try:
        yield xui
    finally:
        await xui.close()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, message.from_user)

    if not user.is_trial_used:
        await message.answer(
            "Привет! Вы можете активировать пробный период и сразу получить доступ к VPN.\n\n"
            f"Длительность trial: {settings.TRIAL_DAYS} дней",
            reply_markup=trial_inline_kb(),
        )
    else:
        await message.answer("Вы уже зарегистрированы. Открываю меню.", reply_markup=main_menu_inline_kb())


@router.message(Command("menu"))
async def menu_handler(message: Message) -> None:
    await message.answer("Меню:", reply_markup=main_menu_inline_kb())


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Помощь\n"
        "/profile — статус подписки\n"
        "/myvpn — ссылка на VPN и управление профилем\n"
        "/traffic — статистика трафика\n"
        "/buy — покупка подписки\n\n"
        "Если возникли вопросы — напишите в поддержку.",
        reply_markup=help_inline_kb(),
    )


@router.message(Command("profile"))
async def profile_handler(message: Message) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, message.from_user)

    await message.answer(_profile_status_text(user), reply_markup=profile_inline_kb())


@router.message(Command("buy"))
async def buy_handler(message: Message) -> None:
    await message.answer(
        "Покупка подписки\n"
        "Периоды: 1 / 3 / 6 / 12 месяцев.\n\n"
        "Сейчас оплата через Telegram Payments будет подключена в следующем этапе разработки.\n"
        "Пока вы можете активировать trial (если он еще не использован) и пользоваться сервисом.",
        reply_markup=main_menu_inline_kb(),
    )


@router.message(Command("myvpn"))
async def myvpn_handler(message: Message) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, message.from_user)

    subscription_active = _is_subscription_active(user)
    has_vless_profile = bool(user.vless_uuid and user.vless_remark)

    if not subscription_active:
        await message.answer(
            "Подписка не активна. Чтобы получить доступ к VPN, активируйте trial или оформите покупку.",
            reply_markup=main_menu_inline_kb(),
        )
        return

    if has_vless_profile:
        # We still show the link only after user clicks "Показать ссылку".
        await message.answer(_myvpn_status_text(user), reply_markup=vpn_inline_kb(has_vless_profile=True, subscription_active=True))
    else:
        await message.answer(
            _myvpn_status_text(user),
            reply_markup=vpn_inline_kb(has_vless_profile=False, subscription_active=True),
        )


@router.message(Command("traffic"))
async def traffic_handler(message: Message) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, message.from_user)

    if not _is_subscription_active(user):
        await message.answer("Подписка не активна — трафик недоступен.", reply_markup=main_menu_inline_kb())
        return

    if not user.vless_uuid:
        await message.answer("Сначала создайте VLESS профиль в разделе «Мой VPN».", reply_markup=main_menu_inline_kb())
        return

    try:
        xui = XUIAPI()
        try:
            traffic = await fetch_and_update_traffic_for_user(session=session, user=user, xui=xui)
        finally:
            await xui.close()
    except ServiceError as e:
        await message.answer(f"Не удалось получить трафик: {e}", reply_markup=main_menu_inline_kb())
        return
    except Exception as e:
        logger.exception("traffic error")
        await message.answer("Произошла ошибка при обращении к XUI. Попробуйте позже.", reply_markup=main_menu_inline_kb())
        return

    await message.answer(
        "Статистика трафика\n"
        f"Upload: {format_bytes_gb(traffic.uploaded_bytes)}\n"
        f"Download: {format_bytes_gb(traffic.downloaded_bytes)}\n"
        f"Total: {format_bytes_gb(traffic.total_bytes)}",
        reply_markup=main_menu_inline_kb(),
    )


@router.callback_query(F.data.startswith("nav:"))
async def nav_callback_handler(call: CallbackQuery) -> None:
    assert call.data is not None
    action = call.data.split(":", 1)[1]
    if action == "menu":
        await call.message.edit_text("Меню:", reply_markup=main_menu_inline_kb())
    elif action == "profile":
        await call.answer()
        await profile_handler(call.message)
    elif action == "myvpn":
        await call.answer()
        await myvpn_handler(call.message)
    elif action == "traffic":
        await call.answer()
        await traffic_handler(call.message)
    elif action == "buy":
        await call.answer()
        await buy_handler(call.message)
    elif action == "help":
        await call.answer()
        await help_handler(call.message)
    else:
        await call.answer("Неизвестное действие.", show_alert=True)


@router.callback_query(F.data == "admin:reset_trial_self")
async def admin_reset_trial_self_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        if not _is_admin_user(user):
            await call.answer("Только для админов.", show_alert=True)
            return

        # Remove client in XUI as part of trial reset.
        if user.vless_uuid:
            xui = XUIAPI()
            try:
                try:
                    await xui.remove_client(inbound_id=settings.INBOUND_ID, client_id=user.vless_uuid)
                except Exception:
                    logger.warning("admin reset trial: failed to remove client from XUI", exc_info=True)
            finally:
                await xui.close()

        await reset_trial_for_user(session, telegram_id=user.telegram_id)

    await call.answer("Готово")
    await call.message.answer(
        "Trial для вашего аккаунта сброшен.\n"
        "Теперь можно снова активировать trial через /start.",
        reply_markup=admin_main_inline_kb(),
    )


@router.callback_query(F.data == "trial:activate")
async def trial_activate_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

        if not user_can_activate_trial(user):
            await call.answer("Пробный период уже был использован.", show_alert=True)
            return

        try:
            xui = XUIAPI()
            try:
                vless_url = await activate_trial_and_create_vless_profile(session=session, user=user, xui=xui)
            finally:
                await xui.close()
        except ServiceError as e:
            await call.answer()
            await call.message.answer(f"Не удалось активировать trial: {e}", reply_markup=main_menu_inline_kb())
            return
        except Exception as e:
            logger.exception("trial activate error")
            await call.answer()
            await call.message.answer(
                "Ошибка при создании VPN в XUI. Попробуйте позже.",
                reply_markup=main_menu_inline_kb(),
            )
            return

    await call.answer()
    await call.message.answer("Trial активирован! Ваш VPN доступен.")
    await call.message.answer("VLESS ссылка:")
    await call.message.answer(vless_url)
    await _send_vless_connection_help(call.message)


@router.callback_query(F.data.startswith("guide:"))
async def guide_platform_callback(call: CallbackQuery) -> None:
    assert call.data is not None
    key = call.data.split(":", 1)[1]
    await call.answer()
    fn = GUIDE_TEXT_BY_PLATFORM.get(key)
    if fn is None:
        await call.message.answer("Неизвестная платформа.")
        return
    await call.message.answer(fn())
    await call.message.answer(RU_ROUTING_HAPP_IMPORT)


@router.callback_query(F.data == "vpn:show")
async def vpn_show_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

    if not _is_subscription_active(user):
        await call.answer("Подписка не активна.", show_alert=True)
        return
    if not user.vless_uuid or not user.vless_remark:
        await call.answer("Профиль еще не создан.", show_alert=True)
        return

    try:
        xui = XUIAPI()
        try:
            inbound = await xui.get_inbound(settings.INBOUND_ID)
            port = inbound.get("port")
            if not isinstance(port, int):
                raise ServiceError("Не удалось определить port во входящем (inbound).")
            vless_url = xui.build_vless_url(
                client_id=user.vless_uuid,
                host=settings.XUI_HOST,
                port=port,
                remark=user.vless_remark,
            )
        finally:
            await xui.close()
    except ServiceError as e:
        await call.answer(str(e), show_alert=True)
        return

    await call.answer()
    await call.message.answer("Ваша VLESS ссылка:")
    await call.message.answer(vless_url)
    await _send_vless_connection_help(call.message)


@router.callback_query(F.data == "vpn:create")
async def vpn_create_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        if not _is_subscription_active(user):
            await call.answer("Подписка не активна.", show_alert=True)
            return

        xui = XUIAPI()
        try:
            try:
                vless_url = await ensure_vless_profile_for_user(session=session, user=user, xui=xui)
            except ServiceError as e:
                await call.answer()
                await call.message.answer(f"Не удалось создать профиль: {e}", reply_markup=main_menu_inline_kb())
                return
        finally:
            await xui.close()

    await call.answer()
    await call.message.answer("Профиль создан.")
    await call.message.answer("VLESS ссылка:")
    await call.message.answer(vless_url)
    await _send_vless_connection_help(call.message)


@router.callback_query(F.data == "vpn:delete")
async def vpn_delete_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

    if not _is_subscription_active(user):
        await call.answer("Подписка не активна.", show_alert=True)
        return
    if not user.vless_uuid:
        await call.answer("Профиль не найден.", show_alert=True)
        return

    await call.answer()
    await call.message.answer(
        "Удаление VLESS профиля — действие обратимо только созданием нового профиля.\n"
        "Удалить сейчас?",
        reply_markup=confirm_delete_vpn_inline_kb(),
    )


@router.callback_query(F.data == "vpn:confirm_delete_yes")
async def vpn_confirm_delete_yes_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

        if not user.vless_uuid:
            await call.answer("Профиль уже отсутствует.", show_alert=True)
            return

        xui = XUIAPI()
        try:
            try:
                await delete_vless_profile_for_user(session=session, user=user, xui=xui)
            except ServiceError as e:
                await call.answer()
                await call.message.answer(f"Не удалось удалить профиль: {e}", reply_markup=main_menu_inline_kb())
                return
        finally:
            await xui.close()

    await call.answer()
    await call.message.answer("Профиль удален. VLESS больше недоступен.", reply_markup=main_menu_inline_kb())


@router.callback_query(F.data == "vpn:confirm_delete_no")
async def vpn_confirm_delete_no_callback(call: CallbackQuery) -> None:
    await call.answer()
    await myvpn_handler(call.message)

