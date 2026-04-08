from __future__ import annotations

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


def vpn_inline_kb(*, has_vless_profile: bool, subscription_active: bool) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []

    if subscription_active:
        if has_vless_profile:
            buttons.append([InlineKeyboardButton(text="Показать ссылку", callback_data="vpn:show")])
            buttons.append([InlineKeyboardButton(text="Удалить профиль", callback_data="vpn:delete")])
        else:
            buttons.append([InlineKeyboardButton(text="Создать VLESS профиль", callback_data="vpn:create")])

    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_vpn_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data="vpn:confirm_delete_yes"),
                InlineKeyboardButton(text="Нет", callback_data="vpn:confirm_delete_no"),
            ]
        ]
    )


def help_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")],
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
