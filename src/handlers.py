from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Optional

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    User as TgUser,
)

from .config import settings
from .database import (
    async_session_factory,
    extend_subscription_for_key,
    get_user_vless_key_owned,
    list_user_vless_keys,
    payment_log_exists_by_telegram_charge,
    reset_trial_for_user,
    save_payment_log,
)
from .functions import XUIAPI
from .admin_handlers import admin_router
from .client_guide import GUIDE_PART1_BY_PLATFORM, routing_message_html
from .keyboards import (
    admin_main_inline_kb,
    buy_key_pick_inline_kb,
    buy_plans_for_key_inline_kb,
    confirm_delete_all_vpn_kb,
    confirm_delete_key_kb,
    help_inline_kb,
    main_menu_inline_kb,
    profile_inline_kb,
    trial_inline_kb,
    vpn_keys_inline_kb,
    vless_connection_help_kb,
)
from .services import (
    ServiceError,
    activate_trial_and_create_vless_profile,
    create_extra_vless_key_trial,
    delete_single_vless_key_for_user,
    delete_vless_profile_for_user,
    ensure_vless_profile_for_user,
    fetch_and_update_traffic_for_user,
    get_or_create_user,
    push_key_expiry_to_xui,
    user_can_activate_trial,
    user_can_add_extra_key_trial,
    _is_subscription_active,
)
from .utils import (
    format_bytes_gb,
    format_datetime_ru,
    format_price_minor,
    trial_extra_deadline_phrase_ru,
    vless_url_as_html_code,
)

logger = logging.getLogger(__name__)

router = Router(name="bot_router")
router.include_router(admin_router)

_RE_VPN_DEL = re.compile(r"^vpn:del:(\d+)$")
_RE_VPN_DEL_YES = re.compile(r"^vpn:del_yes:(\d+)$")
_RE_VPN_DEL_NO = re.compile(r"^vpn:del_no:(\d+)$")
_RE_VPN_SHOW = re.compile(r"^vpn:show:(\d+)$")

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


def _myvpn_status_text(user: Any, *, keys: list[Any]) -> str:
    subscription_active = _is_subscription_active(user)
    lines = [
        "Мой VPN",
        f"Есть активный доступ: {'да' if subscription_active else 'нет'}",
        f"Сводка по аккаунту (макс. срок): {format_datetime_ru(user.subscription_end)}",
        f"Ключей: {len(keys)} из {settings.MAX_VLESS_KEYS}",
    ]
    for i, k in enumerate(keys):
        lines.append(f"  Ключ №{i + 1}: до {format_datetime_ru(k.subscription_end)}")
    return "\n".join(lines)


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
        "/myvpn — ключи VPN (несколько), показать и удалить\n"
        "/traffic — статистика трафика\n"
        "/buy — продление срока выбранного ключа\n\n"
        "Если возникли вопросы — напишите в поддержку.",
        reply_markup=help_inline_kb(),
    )


@router.message(Command("profile"))
async def profile_handler(message: Message, event_user: Optional[TgUser] = None) -> None:
    tg = event_user if event_user is not None else message.from_user
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, tg)

    await message.answer(_profile_status_text(user), reply_markup=profile_inline_kb())


@router.message(Command("buy"))
async def buy_handler(message: Message) -> None:
    cur = settings.CURRENCY
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, message.from_user)
        keys = await list_user_vless_keys(session, user_id=user.id)

        if not keys:
            await message.answer(
                "Сначала создайте хотя бы один ключ в разделе «Мой VPN» (trial или после оплаты).",
                reply_markup=main_menu_inline_kb(),
            )
            return

        pick_rows: list[tuple[str, str]] = []
        for i, k in enumerate(keys):
            label = f"Ключ №{i + 1} · до {format_datetime_ru(k.subscription_end)}"
            if len(label) > 58:
                label = label[:55] + "…"
            pick_rows.append((label, f"buy:pk:{k.id}"))

        await message.answer(
            "Покупка\n\n"
            "Срок доступа считается отдельно для каждого ключа. Выберите ключ, который нужно продлить, "
            "затем срок — откроется счёт Telegram Payments.\n\n"
            f"Цены: 1 мес — {format_price_minor(settings.PRICE_1_MONTH, cur)}; "
            f"3 мес — {format_price_minor(settings.PRICE_3_MONTHS, cur)}; "
            f"6 мес — {format_price_minor(settings.PRICE_6_MONTHS, cur)}; "
            f"12 мес — {format_price_minor(settings.PRICE_12_MONTHS, cur)}.\n\n"
            "Дополнительный ключ на 60 минут — бесплатно в «Мой VPN».\n"
            "Админам: тест без оплаты — «Тест покупки» в /admin.",
            reply_markup=buy_key_pick_inline_kb(pick_rows),
        )


@router.message(Command("myvpn"))
async def myvpn_handler(message: Message, event_user: Optional[TgUser] = None) -> None:
    tg = event_user if event_user is not None else message.from_user
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, tg)
        keys = await list_user_vless_keys(session, user_id=user.id)

        subscription_active = _is_subscription_active(user)
        keys_count = len(keys)
        key_rows = [(k.id, i + 1) for i, k in enumerate(keys)]

        if not subscription_active:
            await message.answer(
                "Подписка не активна. Чтобы получить доступ к VPN, активируйте trial или оформите покупку.",
                reply_markup=main_menu_inline_kb(),
            )
            return

        can_create_first = keys_count == 0
        show_buy_extra = await user_can_add_extra_key_trial(
            session, user=user, keys_count=keys_count
        )
        show_delete_all = keys_count >= 2

        await message.answer(
            _myvpn_status_text(user, keys=keys),
            reply_markup=vpn_keys_inline_kb(
                key_rows=key_rows,
                subscription_active=subscription_active,
                can_create_first_free=can_create_first,
                show_buy_extra=show_buy_extra,
                show_delete_all=show_delete_all,
            ),
        )


@router.message(Command("traffic"))
async def traffic_handler(message: Message, event_user: Optional[TgUser] = None) -> None:
    tg = event_user if event_user is not None else message.from_user
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, tg)

        if not _is_subscription_active(user):
            await message.answer("Подписка не активна — трафик недоступен.", reply_markup=main_menu_inline_kb())
            return

        keys = await list_user_vless_keys(session, user_id=user.id)
        if not keys:
            await message.answer("Сначала создайте ключ в разделе «Мой VPN».", reply_markup=main_menu_inline_kb())
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
    # Для inline-кнопок у call.message.from_user часто бот, не клиент — передаём call.from_user в хендлеры.
    assert call.data is not None
    action = call.data.split(":", 1)[1]
    if action == "menu":
        await call.message.edit_text("Меню:", reply_markup=main_menu_inline_kb())
    elif action == "profile":
        await call.answer()
        await profile_handler(call.message, call.from_user)
    elif action == "myvpn":
        await call.answer()
        await myvpn_handler(call.message, call.from_user)
    elif action == "traffic":
        await call.answer()
        await traffic_handler(call.message, call.from_user)
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

        keys = await list_user_vless_keys(session, user_id=user.id)
        if keys:
            xui = XUIAPI()
            try:
                for k in keys:
                    try:
                        await xui.remove_client(inbound_id=settings.INBOUND_ID, client_id=k.vless_uuid)
                    except Exception:
                        logger.warning(
                            "admin reset trial: failed to remove client from XUI uuid=%s",
                            k.vless_uuid,
                            exc_info=True,
                        )
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
    await call.message.answer(
        "VLESS ссылка:\n\n" + vless_url_as_html_code(vless_url),
        parse_mode="HTML",
    )
    await _send_vless_connection_help(call.message)


@router.callback_query(F.data.startswith("guide:"))
async def guide_platform_callback(call: CallbackQuery) -> None:
    assert call.data is not None
    key = call.data.split(":", 1)[1]
    await call.answer()
    fn = GUIDE_PART1_BY_PLATFORM.get(key)
    if fn is None:
        await call.message.answer("Неизвестная платформа.")
        return
    await call.message.answer(fn())
    await call.message.answer(routing_message_html(), parse_mode="HTML")


@router.callback_query(lambda c: bool(c.data and _RE_VPN_SHOW.match(c.data)))
async def vpn_show_key_callback(call: CallbackQuery) -> None:
    assert call.data is not None
    m = _RE_VPN_SHOW.match(call.data)
    assert m is not None
    key_id = int(m.group(1))

    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        key = await get_user_vless_key_owned(session, key_id=key_id, telegram_id=user.telegram_id)

    if not _is_subscription_active(user):
        await call.answer("Подписка не активна.", show_alert=True)
        return
    if key is None:
        await call.answer("Ключ не найден.", show_alert=True)
        return

    try:
        xui = XUIAPI()
        try:
            inbound = await xui.get_inbound(settings.INBOUND_ID)
            port = inbound.get("port")
            if not isinstance(port, int):
                raise ServiceError("Не удалось определить port во входящем (inbound).")
            reality_params = xui.extract_reality_params_from_inbound(inbound)
            vless_url = xui.build_vless_url(
                client_id=key.vless_uuid,
                host=settings.XUI_HOST,
                port=port,
                remark=key.vless_remark,
                sni=reality_params.get("sni"),
                sid=reality_params.get("sid"),
                spider_x=reality_params.get("spider_x"),
            )
        finally:
            await xui.close()
    except ServiceError as e:
        await call.answer(str(e), show_alert=True)
        return

    await call.answer()
    await call.message.answer(
        "Ваша VLESS ссылка:\n\n" + vless_url_as_html_code(vless_url),
        parse_mode="HTML",
    )
    await _send_vless_connection_help(call.message)


@router.callback_query(F.data == "vpn:create")
async def vpn_create_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        if not _is_subscription_active(user):
            await call.answer("Подписка не активна.", show_alert=True)
            return

        existing = await list_user_vless_keys(session, user_id=user.id)
        if existing:
            await call.answer(
                "Первый ключ уже есть. Дополнительные — кнопка «Доп. ключ (60 мин бесплатно)» в «Мой VPN».",
                show_alert=True,
            )
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
    await call.message.answer(
        "VLESS ссылка:\n\n" + vless_url_as_html_code(vless_url),
        parse_mode="HTML",
    )
    await _send_vless_connection_help(call.message)


@router.callback_query(F.data == "vpn:trial_extra")
async def vpn_trial_extra_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        keys = await list_user_vless_keys(session, user_id=user.id)
        keys_count = len(keys)
        if not await user_can_add_extra_key_trial(session, user=user, keys_count=keys_count):
            await call.answer("Сейчас нельзя добавить дополнительный ключ.", show_alert=True)
            return

        xui = XUIAPI()
        try:
            try:
                vless_url = await create_extra_vless_key_trial(session=session, user=user, xui=xui)
            except ServiceError as e:
                await call.answer(str(e), show_alert=True)
                return
        finally:
            await xui.close()

    await call.answer()
    deadline = trial_extra_deadline_phrase_ru(settings.EXTRA_KEY_TRIAL_MINUTES)
    await call.message.answer(
        "Теперь у вас есть дополнительный ключ:\n\n"
        f"{vless_url_as_html_code(vless_url)}\n\n"
        f"Активируйте его и купите подписку на этот ключ {deadline}, иначе ключ будет удалён.",
        parse_mode="HTML",
    )
    await _send_vless_connection_help(call.message)


@router.callback_query(lambda c: bool(c.data and _RE_VPN_DEL.match(c.data)))
async def vpn_delete_prompt_callback(call: CallbackQuery) -> None:
    assert call.data is not None
    m = _RE_VPN_DEL.match(call.data)
    assert m is not None
    key_id = int(m.group(1))

    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

    if not _is_subscription_active(user):
        await call.answer("Подписка не активна.", show_alert=True)
        return

    await call.answer()
    await call.message.answer(
        "Удалить этот ключ? Действие обратимо только созданием нового ключа.",
        reply_markup=confirm_delete_key_kb(key_id=key_id),
    )


@router.callback_query(lambda c: bool(c.data and _RE_VPN_DEL_YES.match(c.data)))
async def vpn_delete_yes_callback(call: CallbackQuery) -> None:
    assert call.data is not None
    m = _RE_VPN_DEL_YES.match(call.data)
    assert m is not None
    key_id = int(m.group(1))

    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

        xui = XUIAPI()
        try:
            try:
                await delete_single_vless_key_for_user(session=session, user=user, key_id=key_id, xui=xui)
            except ServiceError as e:
                await call.answer()
                await call.message.answer(f"Не удалось удалить ключ: {e}", reply_markup=main_menu_inline_kb())
                return
        finally:
            await xui.close()

    await call.answer()
    await call.message.answer("Ключ удалён.", reply_markup=main_menu_inline_kb())


@router.callback_query(lambda c: bool(c.data and _RE_VPN_DEL_NO.match(c.data)))
async def vpn_delete_no_callback(call: CallbackQuery) -> None:
    await call.answer()
    await myvpn_handler(call.message, call.from_user)


@router.callback_query(F.data == "vpn:delete_all")
async def vpn_delete_all_prompt_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        keys = await list_user_vless_keys(session, user_id=user.id)

    if not _is_subscription_active(user):
        await call.answer("Подписка не активна.", show_alert=True)
        return
    if len(keys) < 2:
        await call.answer("Несколько ключей не найдено.", show_alert=True)
        return

    await call.answer()
    await call.message.answer(
        "Удалить все VLESS-ключи? Подписка в боте сохранится.",
        reply_markup=confirm_delete_all_vpn_kb(),
    )


@router.callback_query(F.data == "vpn:del_all_yes")
async def vpn_delete_all_yes_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)

        xui = XUIAPI()
        try:
            try:
                await delete_vless_profile_for_user(session=session, user=user, xui=xui)
            except ServiceError as e:
                await call.answer()
                await call.message.answer(f"Не удалось удалить ключи: {e}", reply_markup=main_menu_inline_kb())
                return
        finally:
            await xui.close()

    await call.answer()
    await call.message.answer("Все ключи удалены.", reply_markup=main_menu_inline_kb())


@router.callback_query(F.data == "vpn:del_all_no")
async def vpn_delete_all_no_callback(call: CallbackQuery) -> None:
    await call.answer()
    await myvpn_handler(call.message, call.from_user)


def _parse_buy_invoice_callback(data: str) -> Optional[tuple[int, int, int, str, int]]:
    """Возвращает (months, amount, label_short, payload, key_id) или None."""

    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "buy" or parts[1] != "inv":
        return None
    rcode, kid_s = parts[2], parts[3]
    try:
        key_id = int(kid_s)
    except ValueError:
        return None
    row = {
        "r1": (1, settings.PRICE_1_MONTH, "Продление 1 мес"),
        "r3": (3, settings.PRICE_3_MONTHS, "Продление 3 мес"),
        "r6": (6, settings.PRICE_6_MONTHS, "Продление 6 мес"),
        "r12": (12, settings.PRICE_12_MONTHS, "Продление 12 мес"),
    }.get(rcode)
    if row is None:
        return None
    months, amount, label = row
    payload = f"{rcode}:{key_id}"
    return months, amount, label, payload, key_id


@router.callback_query(F.data.startswith("buy:pk:"))
async def buy_pick_key_callback(call: CallbackQuery) -> None:
    assert call.data is not None
    try:
        key_id = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        await call.answer("Некорректный ключ.", show_alert=True)
        return

    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        row = await get_user_vless_key_owned(session, key_id=key_id, telegram_id=user.telegram_id)
        if row is None:
            await call.answer("Ключ не найден.", show_alert=True)
            return

    await call.answer()
    text = "Выберите срок продления для этого ключа (счёт Telegram Payments)."
    try:
        await call.message.edit_text(
            text,
            reply_markup=buy_plans_for_key_inline_kb(key_id=key_id),
        )
    except Exception:
        await call.message.answer(
            text,
            reply_markup=buy_plans_for_key_inline_kb(key_id=key_id),
        )


@router.callback_query(F.data == "buy:back_keys")
async def buy_back_to_keys_callback(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        keys = await list_user_vless_keys(session, user_id=user.id)

        if not keys:
            await call.answer()
            await call.message.edit_text("Ключей нет.", reply_markup=main_menu_inline_kb())
            return

        pick_rows: list[tuple[str, str]] = []
        for i, k in enumerate(keys):
            label = f"Ключ №{i + 1} · до {format_datetime_ru(k.subscription_end)}"
            if len(label) > 58:
                label = label[:55] + "…"
            pick_rows.append((label, f"buy:pk:{k.id}"))

    await call.answer()
    try:
        await call.message.edit_text(
            "Выберите ключ для продления:",
            reply_markup=buy_key_pick_inline_kb(pick_rows),
        )
    except Exception:
        await call.message.answer(
            "Выберите ключ для продления:",
            reply_markup=buy_key_pick_inline_kb(pick_rows),
        )


@router.callback_query(F.data.startswith("buy:inv:"))
async def buy_invoice_for_key_callback(call: CallbackQuery, bot: Bot) -> None:
    assert call.data is not None
    parsed = _parse_buy_invoice_callback(call.data)
    if parsed is None:
        await call.answer("Неизвестный тариф.", show_alert=True)
        return

    months, amount, label, payload, key_id = parsed

    async with async_session_factory() as session:
        user = await _get_user_for_message(session, call.from_user)
        row = await get_user_vless_key_owned(session, key_id=key_id, telegram_id=user.telegram_id)
        if row is None:
            await call.answer("Ключ не найден.", show_alert=True)
            return

    await call.answer()
    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title=label,
        description=f"Продление ключа на {months} мес.",
        payload=payload,
        provider_token=settings.PAYMENT_TOKEN,
        currency=settings.CURRENCY,
        prices=[LabeledPrice(label=label, amount=amount)],
    )


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload or ""
    try:
        if ":" not in payload:
            await pre_checkout_query.answer(ok=False, error_message="Неизвестный тариф.")
            return
        plan_code, _, key_id_s = payload.rpartition(":")
        if not plan_code or not key_id_s:
            await pre_checkout_query.answer(ok=False, error_message="Неизвестный тариф.")
            return
        try:
            key_id = int(key_id_s)
        except ValueError:
            await pre_checkout_query.answer(ok=False, error_message="Неизвестный тариф.")
            return
        if plan_code not in ("r1", "r3", "r6", "r12"):
            await pre_checkout_query.answer(ok=False, error_message="Неизвестный тариф.")
            return

        async with async_session_factory() as session:
            user = await _get_user_for_message(session, pre_checkout_query.from_user)
            row = await get_user_vless_key_owned(
                session, key_id=key_id, telegram_id=user.telegram_id
            )
            if row is None:
                await pre_checkout_query.answer(ok=False, error_message="Ключ не найден.")
                return
    except Exception:
        logger.exception("pre_checkout_query")
        await pre_checkout_query.answer(ok=False, error_message="Ошибка проверки. Попробуйте позже.")
        return

    await pre_checkout_query.answer(ok=True)


@router.message(lambda m: m.successful_payment is not None)
async def successful_payment_handler(message: Message) -> None:
    sp = message.successful_payment
    if sp is None:
        return

    charge_id = sp.telegram_payment_charge_id or ""
    async with async_session_factory() as session:
        if charge_id and await payment_log_exists_by_telegram_charge(session, charge_id=charge_id):
            return

        user = await _get_user_for_message(session, message.from_user)
        payload = sp.invoice_payload

        try:
            if ":" not in (payload or ""):
                await message.answer("Неизвестный тип платежа.")
                return
            plan_code, _, key_id_s = (payload or "").rpartition(":")
            months_map = {"r1": 1, "r3": 3, "r6": 6, "r12": 12}
            months = months_map.get(plan_code)
            if months is None:
                await message.answer("Неизвестный тип платежа.")
                return
            try:
                key_id = int(key_id_s)
            except ValueError:
                await message.answer("Неизвестный тип платежа.")
                return

            xui = XUIAPI()
            try:
                user_after, key_row = await extend_subscription_for_key(
                    session,
                    telegram_id=user.telegram_id,
                    key_id=key_id,
                    months=months,
                )
                await push_key_expiry_to_xui(
                    xui,
                    vless_uuid=key_row.vless_uuid,
                    vless_email=key_row.vless_email,
                    subscription_end=key_row.subscription_end,
                )
            finally:
                await xui.close()

            await save_payment_log(
                session,
                telegram_id=user.telegram_id,
                amount=sp.total_amount,
                currency=(sp.currency or settings.CURRENCY).upper(),
                plan_code=f"renew_key_{months}m",
                months=months,
                payload=payload or "",
                provider_payment_charge_id=sp.provider_payment_charge_id,
                telegram_payment_charge_id=sp.telegram_payment_charge_id,
                status="completed",
            )
            await message.answer(
                f"Оплата принята. Срок выбранного ключа продлён на {months} мес.\n"
                f"Окончание ключа: {format_datetime_ru(key_row.subscription_end)}\n"
                f"Сводка по аккаунту: {format_datetime_ru(user_after.subscription_end)}",
                reply_markup=main_menu_inline_kb(),
            )
        except Exception as e:
            logger.exception("successful_payment")
            await message.answer(
                f"Платёж получен, но применить изменения не удалось: {e}. "
                "Сохраните скриншот и напишите в поддержку.",
                reply_markup=main_menu_inline_kb(),
            )

