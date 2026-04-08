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


def admin_menu_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сбросить trial себе", callback_data="admin:reset_trial_self")],
            [InlineKeyboardButton(text="Назад в меню", callback_data="nav:menu")],
        ]
    )

