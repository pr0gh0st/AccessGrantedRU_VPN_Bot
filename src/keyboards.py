from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Профиль", callback_data="nav:profile")],
            [InlineKeyboardButton(text="Мой VPN", callback_data="nav:myvpn")],
            [InlineKeyboardButton(text="Трафик", callback_data="nav:traffic")],
            [InlineKeyboardButton(text="Купить подписку", callback_data="nav:buy")],
            [InlineKeyboardButton(text="Помощь", callback_data="nav:help")],
        ]
    )


def trial_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Активировать trial", callback_data="trial:activate")],
        ]
    )


def profile_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")],
        ]
    )


def vpn_keys_inline_kb(
    *,
    key_rows: Sequence[tuple[int, int]],
    subscription_active: bool,
    can_create_first_free: bool,
    show_buy_extra: bool,
    show_delete_all: bool,
) -> InlineKeyboardMarkup:
    """key_rows: (key_id, номер для отображения)."""

    buttons: list[list[InlineKeyboardButton]] = []

    if subscription_active:
        for key_id, num in key_rows:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Показать ключ №{num}",
                        callback_data=f"vpn:show:{key_id}",
                    ),
                    InlineKeyboardButton(
                        text=f"Удалить №{num}",
                        callback_data=f"vpn:del:{key_id}",
                    ),
                ]
            )
        if can_create_first_free:
            buttons.append([InlineKeyboardButton(text="Создать первый ключ", callback_data="vpn:create")])
        if show_buy_extra:
            buttons.append([InlineKeyboardButton(text="Купить доп. ключ", callback_data="buy:inv:ek")])
        if show_delete_all:
            buttons.append([InlineKeyboardButton(text="Удалить все ключи", callback_data="vpn:delete_all")])

    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_key_kb(*, key_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"vpn:del_yes:{key_id}"),
                InlineKeyboardButton(text="Нет", callback_data=f"vpn:del_no:{key_id}"),
            ]
        ]
    )


def confirm_delete_all_vpn_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить все", callback_data="vpn:del_all_yes"),
                InlineKeyboardButton(text="Нет", callback_data="vpn:del_all_no"),
            ]
        ]
    )


def buy_plans_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Доп. ключ VPN", callback_data="buy:inv:ek")],
            [
                InlineKeyboardButton(text="1 мес", callback_data="buy:inv:r1"),
                InlineKeyboardButton(text="3 мес", callback_data="buy:inv:r3"),
            ],
            [
                InlineKeyboardButton(text="6 мес", callback_data="buy:inv:r6"),
                InlineKeyboardButton(text="12 мес", callback_data="buy:inv:r12"),
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data="nav:menu")],
        ]
    )


def help_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")],
        ]
    )


def vless_connection_help_kb() -> InlineKeyboardMarkup:
    """Кнопки выбора ОС после выдачи VLESS-ссылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1. Windows", callback_data="guide:win"),
                InlineKeyboardButton(text="2. Linux", callback_data="guide:linux"),
            ],
            [
                InlineKeyboardButton(text="3. Mac", callback_data="guide:mac"),
                InlineKeyboardButton(text="4. iOS", callback_data="guide:ios"),
            ],
            [InlineKeyboardButton(text="5. Android", callback_data="guide:android")],
            [InlineKeyboardButton(text="Главное меню", callback_data="nav:menu")],
        ]
    )


def admin_main_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пользователи", callback_data="admin:users:0")],
            [InlineKeyboardButton(text="Найти пользователя", callback_data="admin:search")],
            [
                InlineKeyboardButton(text="+ дни", callback_data="admin:add_days"),
                InlineKeyboardButton(text="− дни", callback_data="admin:sub_days"),
            ],
            [InlineKeyboardButton(text="Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="Статические профили", callback_data="admin:static")],
            [InlineKeyboardButton(text="Платежи", callback_data="admin:payments")],
            [InlineKeyboardButton(text="Сбросить trial себе", callback_data="admin:reset_trial_self")],
            [InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")],
        ]
    )


def admin_users_nav_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton(text="←", callback_data=f"admin:users:{page - 1}"))
    row.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{max(total_pages, 1)}",
            callback_data="admin:noop",
        )
    )
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(text="→", callback_data=f"admin:users:{page + 1}"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text="Админ-меню", callback_data="admin:menu")],
        ]
    )


def admin_static_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Список", callback_data="admin:static:list")],
            [InlineKeyboardButton(text="Добавить", callback_data="admin:static:add")],
            [InlineKeyboardButton(text="Админ-меню", callback_data="admin:menu")],
        ]
    )


def admin_cancel_fsm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="admin:cancel_fsm")],
        ]
    )
