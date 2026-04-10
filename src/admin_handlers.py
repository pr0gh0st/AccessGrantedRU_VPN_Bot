from __future__ import annotations

import logging
import math
from typing import Any, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import settings
from .database import (
    add_static_profile,
    async_session_factory,
    count_user_vless_keys,
    count_users_expired_subscription,
    count_users_trial_used,
    count_users_total,
    count_users_with_active_subscription,
    delete_static_profile,
    extend_subscription,
    extend_subscription_by_days,
    get_all_telegram_ids,
    get_all_users,
    get_recent_payment_logs,
    list_static_profiles,
    list_user_vless_keys,
    save_admin_broadcast_log,
    search_user_by_telegram_id,
    search_users_by_username,
    sum_payment_amounts_successful,
)
from .functions import XUIAPI
from .keyboards import (
    admin_buy_sim_inline_kb,
    admin_cancel_fsm_kb,
    admin_main_inline_kb,
    admin_static_menu_kb,
    admin_users_nav_kb,
    vless_connection_help_kb,
)
from .services import (
    ServiceError,
    _is_subscription_active,
    create_extra_vless_key_after_payment,
    format_admin_user_card,
    get_or_create_user,
    user_can_buy_extra_key,
)
from .utils import format_datetime_ru, format_price_minor, vless_url_as_html_code

logger = logging.getLogger(__name__)

admin_router = Router(name="admin_router")

USERS_PAGE_SIZE = 5


def _admin_buy_sim_menu_caption() -> str:
    cur = settings.CURRENCY
    return (
        "Меню покупки — тест без оплаты\n\n"
        "Действия применяются к вашему аккаунту (как после успешной оплаты), "
        "без Telegram Payments — для отладки меню.\n\n"
        f"Цены как у пользователей: доп. ключ — {format_price_minor(settings.PRICE_EXTRA_VLESS_KEY, cur)}; "
        f"1 мес — {format_price_minor(settings.PRICE_1_MONTH, cur)}; "
        f"3 мес — {format_price_minor(settings.PRICE_3_MONTHS, cur)}; "
        f"6 мес — {format_price_minor(settings.PRICE_6_MONTHS, cur)}; "
        f"12 мес — {format_price_minor(settings.PRICE_12_MONTHS, cur)}."
    )


class AdminStates(StatesGroup):
    search_query = State()
    add_days_telegram = State()
    add_days_value = State()
    sub_days_telegram = State()
    sub_days_value = State()
    broadcast_text = State()
    static_name = State()
    static_url = State()


def _is_admin(user: Any) -> bool:
    return bool(user.is_admin or (user.telegram_id in settings.admin_ids))


async def _load_admin_user(message: Message) -> Any:
    async with async_session_factory() as session:
        return await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )


async def _load_admin_user_from_call(call: CallbackQuery) -> Any:
    async with async_session_factory() as session:
        return await get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            full_name=call.from_user.full_name,
        )


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await message.answer("Доступ запрещён. Только для администраторов.")
        return
    await message.answer("Админ-панель", reply_markup=admin_main_inline_kb())


@admin_router.message(Command("admin_shop"))
async def cmd_admin_shop(message: Message) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await message.answer("Доступ запрещён. Только для администраторов.")
        return
    await message.answer(_admin_buy_sim_menu_caption(), reply_markup=admin_buy_sim_inline_kb())


@admin_router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await call.answer()
    try:
        await call.message.edit_text("Админ-панель", reply_markup=admin_main_inline_kb())
    except Exception:
        await call.message.answer("Админ-панель", reply_markup=admin_main_inline_kb())


@admin_router.callback_query(F.data == "admin:noop")
async def cb_admin_noop(call: CallbackQuery) -> None:
    await call.answer()


@admin_router.callback_query(F.data == "admin:buy_sim_menu")
async def cb_admin_buy_sim_menu(call: CallbackQuery) -> None:
    async with async_session_factory() as session:
        u = await get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            full_name=call.from_user.full_name,
        )
        if not _is_admin(u):
            await call.answer("Нет доступа", show_alert=True)
            return

    await call.answer()
    text = _admin_buy_sim_menu_caption()
    try:
        await call.message.edit_text(text, reply_markup=admin_buy_sim_inline_kb())
    except Exception:
        await call.message.answer(text, reply_markup=admin_buy_sim_inline_kb())


@admin_router.callback_query(F.data.startswith("admin:buy_sim:"))
async def cb_admin_buy_sim_apply(call: CallbackQuery) -> None:
    assert call.data is not None
    part = call.data.split(":")[-1]

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            full_name=call.from_user.full_name,
        )
        if not _is_admin(user):
            await call.answer("Нет доступа", show_alert=True)
            return

        if part == "ek":
            keys = await list_user_vless_keys(session, user_id=user.id)
            if not _is_subscription_active(user):
                await call.answer("Нужна активная подписка.", show_alert=True)
                return
            if len(keys) < 1:
                await call.answer("Сначала создайте первый ключ в «Мой VPN».", show_alert=True)
                return
            if not user_can_buy_extra_key(user=user, keys_count=len(keys)):
                await call.answer("Достигнут лимит ключей.", show_alert=True)
                return

            xui = XUIAPI()
            try:
                try:
                    url = await create_extra_vless_key_after_payment(
                        session=session, user=user, xui=xui
                    )
                except ServiceError as e:
                    await call.answer(str(e), show_alert=True)
                    return
            finally:
                await xui.close()

            await call.answer("Ключ добавлен (тест)")
            await call.message.answer(
                "[Тест, без оплаты] Новый ключ:\n\n" + vless_url_as_html_code(url),
                parse_mode="HTML",
            )
            await call.message.answer(
                "Теперь Вы можете скопировать ссылку в Ваше приложение\n\n"
                "Выберите платформу для инструкции:",
                reply_markup=vless_connection_help_kb(),
            )
            return

        months_map = {"r1": 1, "r3": 3, "r6": 6, "r12": 12}
        months = months_map.get(part)
        if months is None:
            await call.answer("Неизвестный вариант.", show_alert=True)
            return

        user_after = await extend_subscription(
            session, telegram_id=user.telegram_id, months=months
        )
        await call.answer("Готово")
        await call.message.answer(
            f"[Тест, без оплаты] Подписка продлена на {months} мес.\n"
            f"Окончание: {format_datetime_ru(user_after.subscription_end)}",
            reply_markup=admin_main_inline_kb(),
        )


@admin_router.callback_query(F.data.startswith("admin:users:"))
async def cb_admin_users(call: CallbackQuery) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    page = int(call.data.split(":")[2])
    async with async_session_factory() as session:
        total = await count_users_total(session)
        total_pages = max(1, math.ceil(total / USERS_PAGE_SIZE) if total else 1)
        page = max(0, min(page, total_pages - 1))
        offset = page * USERS_PAGE_SIZE
        users = await get_all_users(session, offset=offset, limit=USERS_PAGE_SIZE)

    lines = [f"Пользователи (стр. {page + 1}/{total_pages}), всего в БД: {total}\n"]
    for u in users:
        un = f"@{u.username}" if u.username else "—"
        lines.append(f"• `{u.telegram_id}` {un} | trial:{ 'да' if u.is_trial_used else 'нет'}")

    text = "\n".join(lines) if users else "Список пуст."
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=admin_users_nav_kb(page=page, total_pages=total_pages))
    except Exception:
        await call.message.answer(text, reply_markup=admin_users_nav_kb(page=page, total_pages=total_pages))


@admin_router.callback_query(F.data == "admin:search")
async def cb_admin_search(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.search_query)
    await call.answer()
    await call.message.answer(
        "Введите Telegram ID (число) или часть username (без @):\n"
        "Или нажмите «Отмена».",
        reply_markup=admin_cancel_fsm_kb(),
    )


@admin_router.message(AdminStates.search_query, F.text)
async def msg_admin_search(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    q = (message.text or "").strip()
    await state.clear()
    async with async_session_factory() as session:
        if q.isdigit():
            u = await search_user_by_telegram_id(session, int(q))
            if not u:
                await message.answer("Пользователь не найден.", reply_markup=admin_main_inline_kb())
                return
            kc = await count_user_vless_keys(session, user_id=u.id)
            await message.answer(
                format_admin_user_card(u, vless_keys_count=kc), reply_markup=admin_main_inline_kb()
            )
            return
        found = await search_users_by_username(session, username_query=q, limit=8)
        if not found:
            await message.answer("Никого не найдено.", reply_markup=admin_main_inline_kb())
            return
        parts = []
        for u in found:
            kc = await count_user_vless_keys(session, user_id=u.id)
            parts.append(format_admin_user_card(u, vless_keys_count=kc))
        text = "\n\n---\n\n".join(parts)
        if len(text) > 3800:
            text = text[:3800] + "\n…(обрезано)"
        await message.answer(text, reply_markup=admin_main_inline_kb())


@admin_router.callback_query(F.data == "admin:add_days")
async def cb_admin_add_days(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.add_days_telegram)
    await call.answer()
    await call.message.answer(
        "Добавление дней подписки.\nВведите Telegram ID пользователя:",
        reply_markup=admin_cancel_fsm_kb(),
    )


@admin_router.message(AdminStates.add_days_telegram, F.text)
async def msg_admin_add_days_tg(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    if not (message.text or "").strip().isdigit():
        await message.answer("Нужно число — Telegram ID.")
        return
    await state.update_data(target_tg=int(message.text.strip()))
    await state.set_state(AdminStates.add_days_value)
    await message.answer("Сколько дней добавить? (целое число)", reply_markup=admin_cancel_fsm_kb())


@admin_router.message(AdminStates.add_days_value, F.text)
async def msg_admin_add_days_val(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    try:
        days = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число дней.")
        return
    if days <= 0:
        await message.answer("Число дней должно быть > 0.")
        return
    data = await state.get_data()
    tg = int(data["target_tg"])
    await state.clear()
    try:
        async with async_session_factory() as session:
            u = await extend_subscription_by_days(session, telegram_id=tg, days=days)
        await message.answer(
            f"Готово. Пользователь `{u.telegram_id}`: подписка до {format_datetime_ru(u.subscription_end)}",
            reply_markup=admin_main_inline_kb(),
        )
    except LookupError:
        await message.answer("Пользователь не найден.", reply_markup=admin_main_inline_kb())
    except Exception as e:
        await message.answer(f"Ошибка: {e}", reply_markup=admin_main_inline_kb())


@admin_router.callback_query(F.data == "admin:sub_days")
async def cb_admin_sub_days(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.sub_days_telegram)
    await call.answer()
    await call.message.answer(
        "Уменьшение дней подписки.\nВведите Telegram ID пользователя:",
        reply_markup=admin_cancel_fsm_kb(),
    )


@admin_router.message(AdminStates.sub_days_telegram, F.text)
async def msg_admin_sub_days_tg(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    if not (message.text or "").strip().isdigit():
        await message.answer("Нужно число — Telegram ID.")
        return
    await state.update_data(target_tg=int(message.text.strip()))
    await state.set_state(AdminStates.sub_days_value)
    await message.answer("Сколько дней отнять? (целое число)", reply_markup=admin_cancel_fsm_kb())


@admin_router.message(AdminStates.sub_days_value, F.text)
async def msg_admin_sub_days_val(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    try:
        days = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число дней.")
        return
    if days <= 0:
        await message.answer("Число дней должно быть > 0.")
        return
    data = await state.get_data()
    tg = int(data["target_tg"])
    await state.clear()
    try:
        async with async_session_factory() as session:
            u = await extend_subscription_by_days(session, telegram_id=tg, days=-days)
        await message.answer(
            f"Готово. Пользователь `{u.telegram_id}`: подписка до {format_datetime_ru(u.subscription_end)}, активен: {u.is_active}",
            reply_markup=admin_main_inline_kb(),
        )
    except LookupError:
        await message.answer("Пользователь не найден.", reply_markup=admin_main_inline_kb())
    except ValueError as e:
        await message.answer(str(e), reply_markup=admin_main_inline_kb())
    except Exception as e:
        await message.answer(f"Ошибка: {e}", reply_markup=admin_main_inline_kb())


@admin_router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(call: CallbackQuery) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    async with async_session_factory() as session:
        total = await count_users_total(session)
        active = await count_users_with_active_subscription(session)
        trial_cnt = await count_users_trial_used(session)
        expired = await count_users_expired_subscription(session)
        pay_sum = await sum_payment_amounts_successful(session)
        recent = await get_recent_payment_logs(session, limit=10)

    lines = [
        "Статистика",
        f"Всего пользователей: {total}",
        f"С активной подпиской: {active}",
        f"Использовали trial: {trial_cnt}",
        f"С истёкшей подпиской (дата в прошлом): {expired}",
        f"Сумма успешных оплат (по статусам): {pay_sum} (минорные ед. валюты)",
        "",
        "Последние платежи:",
    ]
    if not recent:
        lines.append("— записей нет —")
    else:
        for p in recent:
            lines.append(
                f"#{p.id} tg `{p.telegram_id}` | {p.amount} {p.currency} | {p.status} | {p.plan_code}"
            )
    text = "\n".join(lines)
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=admin_main_inline_kb())
    except Exception:
        await call.message.answer(text, reply_markup=admin_main_inline_kb())


@admin_router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast_text)
    await call.answer()
    await call.message.answer(
        "Рассылка всем пользователям.\nОтправьте текст сообщения одним сообщением.\nИли «Отмена».",
        reply_markup=admin_cancel_fsm_kb(),
    )


@admin_router.message(AdminStates.broadcast_text, F.text)
async def msg_admin_broadcast(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой текст.")
        return
    await state.clear()

    async with async_session_factory() as session:
        ids = await get_all_telegram_ids(session)
        total = len(ids)

    ok = 0
    fail = 0
    for chat_id in ids:
        try:
            await message.bot.send_message(chat_id=chat_id, text=text)
            ok += 1
        except TelegramAPIError:
            fail += 1
        except Exception:
            fail += 1

    async with async_session_factory() as session:
        await save_admin_broadcast_log(
            session,
            text=text,
            total_users=total,
            success_count=ok,
            fail_count=fail,
        )

    await message.answer(
        f"Рассылка завершена.\nВсего: {total}\nУспешно: {ok}\nОшибок: {fail}",
        reply_markup=admin_main_inline_kb(),
    )


@admin_router.callback_query(F.data == "admin:static")
async def cb_admin_static_menu(call: CallbackQuery) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()
    try:
        await call.message.edit_text("Статические профили", reply_markup=admin_static_menu_kb())
    except Exception:
        await call.message.answer("Статические профили", reply_markup=admin_static_menu_kb())


@admin_router.callback_query(F.data == "admin:static:list")
async def cb_admin_static_list(call: CallbackQuery) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    async with async_session_factory() as session:
        items = await list_static_profiles(session)
    if not items:
        txt = "Список пуст."
    else:
        chunks = []
        for p in items:
            url = p.vless_url if len(p.vless_url) <= 500 else p.vless_url[:500] + "…"
            chunks.append(f"#{p.id} {p.name}\n{url}")
        txt = "\n\n".join(chunks)
    rows: list[list[InlineKeyboardButton]] = []
    for p in items:
        rows.append([InlineKeyboardButton(text=f"Удалить #{p.id}", callback_data=f"admin:static:del:{p.id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:static")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows) if items else admin_static_menu_kb()
    await call.answer()
    try:
        await call.message.edit_text(txt, reply_markup=kb)
    except Exception:
        await call.message.answer(txt, reply_markup=kb)


@admin_router.callback_query(F.data == "admin:static:add")
async def cb_admin_static_add(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.static_name)
    await call.answer()
    await call.message.answer("Имя профиля (уникальное):", reply_markup=admin_cancel_fsm_kb())


@admin_router.message(AdminStates.static_name, F.text)
async def msg_admin_static_name(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await state.update_data(static_name=name)
    await state.set_state(AdminStates.static_url)
    await message.answer("VLESS URL (полная ссылка):", reply_markup=admin_cancel_fsm_kb())


@admin_router.message(AdminStates.static_url, F.text)
async def msg_admin_static_url(message: Message, state: FSMContext) -> None:
    user = await _load_admin_user(message)
    if not _is_admin(user):
        await state.clear()
        return
    url = (message.text or "").strip()
    if not url.startswith("vless://"):
        await message.answer("Ожидается ссылка vless://...")
        return
    data = await state.get_data()
    name = data.get("static_name", "")
    await state.clear()
    try:
        async with async_session_factory() as session:
            await add_static_profile(session, name=name, vless_url=url)
        await message.answer(f"Профиль «{name}» добавлен.", reply_markup=admin_static_menu_kb())
    except Exception as e:
        await message.answer(f"Ошибка: {e}", reply_markup=admin_static_menu_kb())


@admin_router.callback_query(F.data.startswith("admin:static:del:"))
async def cb_admin_static_del(call: CallbackQuery) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    pid = int(call.data.split(":")[3])
    async with async_session_factory() as session:
        await delete_static_profile(session, profile_id=pid)
    await call.answer("Удалено")
    await cb_admin_static_list(call)


@admin_router.callback_query(F.data == "admin:payments")
async def cb_admin_payments(call: CallbackQuery) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    async with async_session_factory() as session:
        logs = await get_recent_payment_logs(session, limit=30)
        total_sum = await sum_payment_amounts_successful(session)
    lines = [f"Последние платежи (успешная сумма всего: {total_sum})\n"]
    if not logs:
        lines.append("Записей нет.")
    else:
        for p in logs:
            lines.append(
                f"#{p.id} `{p.telegram_id}` | {p.amount} {p.currency} | {p.status} | {p.plan_code} | {p.created_at}"
            )
    text = "\n".join(lines)
    await call.answer()
    try:
        await call.message.edit_text(text[:4000], reply_markup=admin_main_inline_kb())
    except Exception:
        await call.message.answer(text[:4000], reply_markup=admin_main_inline_kb())


@admin_router.callback_query(F.data == "admin:cancel_fsm")
async def cb_admin_cancel_fsm(call: CallbackQuery, state: FSMContext) -> None:
    user = await _load_admin_user_from_call(call)
    if not _is_admin(user):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await call.answer("Отменено")
    try:
        await call.message.edit_text("Админ-панель", reply_markup=admin_main_inline_kb())
    except Exception:
        await call.message.answer("Админ-панель", reply_markup=admin_main_inline_kb())


@admin_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if not cur:
        return
    user = await _load_admin_user(message)
    if not _is_admin(user):
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=admin_main_inline_kb())
