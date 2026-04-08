"""Ссылки и тексты помощи по подключению Happ / VLESS (без секретов панели)."""

from __future__ import annotations

import html as html_module

# Happ — установщики и магазины
HAPP_WINDOWS_SETUP_URL = (
    "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"
)
HAPP_LINUX_DEB_URL = (
    "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb"
)
HAPP_MAC_APP_STORE_URL = "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"
HAPP_IOS_APP_STORE_URL = "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"
HAPP_ANDROID_PLAY_URL = "https://play.google.com/store/apps/details?id=com.happproxy"

# Импорт RU-маршрутов (happ:// — открытие в Happ / копирование длинного тапа по ссылке)
RU_ROUTING_HAPP_IMPORT = (
    "happ://routing/add/eyJSb3V0ZU9yZGVyIjoiYmxvY2stZGlyZWN0LXByb3h5IiwiRG9tZXN0aWNETlNUeXBlIjoiRG9VIiwiUmVtb3RlRE5TVHlwZSI6IkRvVSIsIkRuc0hvc3RzIjp7fSwiUHJveHlTaXRlcyI6W10sIkRvbWVzdGljRE5TRG9tYWluIjoiaHR0cHM6XC9cL2Rucy5nb29nbGVcL2Rucy1xdWVyeSIsIkdlb2lwVXJsIjoiaHR0cHM6XC9cL2dpdGh1Yi5jb21cL0xveWFsc29sZGllclwvdjJyYXktcnVsZXMtZGF0XC9yZWxlYXNlc1wvbGF0ZXN0XC9kb3dubG9hZFwvZ2VvaXAuZGF0IiwiQmxvY2tJcCI6W10sIlJlbW90ZUROU0RvbWFpbiI6Imh0dHBzOlwvXC9jbG91ZGZsYXJlLWRucy5jb21cL2Rucy1xdWVyeSIsIkRpcmVjdFNpdGVzIjpbImdlb3NpdGU6Y2F0ZWdvcnktcnUiXSwiUHJveHlJcCI6W10sIlVzZUNodW5rRmlsZXMiOnRydWUsIkxhc3RVcGRhdGVkIjoxNzc1NjQ0NzQ0LCJEaXJlY3RJcCI6WyIxMC4wLjAuMFwvOCIsIjEwMC42NC4wLjBcLzEwIiwiMTcyLjE2LjAuMFwvMTIiLCIxOTIuMTY4LjAuMFwvMTYiLCIxNjkuMjU0LjAuMFwvMTYiLCIyMjQuMC4wLjBcLzQiLCIyNTUuMjU1LjI1NS4yNTUiLCJnZW9pcDpydSJdLCJCbG9ja1NpdGVzIjpbXSwiUmVtb3RlRE5TSXAiOiIxLjEuMS4xIiwiRG9tZXN0aWNETlNJcCI6IjguOC44LjgiLCJHZW9zaXRlVXJsIjoiaHR0cHM6XC9cL2dpdGh1Yi5jb21cL0xveWFsc29sZGllclwvdjJyYXktcnVsZXMtZGF0XC9yZWxlYXNlc1wvbGF0ZXN0XC9kb3dubG9hZFwvZ2Vvc2l0ZS5kYXQiLCJOYW1lIjoiUlVub3RWUE4iLCJGYWtlRG5zIjpmYWxzZX0="
)

# Шаги в интерфейсе Happ после перехода по ссылке (или при ручном импорте)
ROUTING_UI_STEPS_RU = (
    "Как добавить в приложение:\n"
    "Настройки → Правила маршрутизации → три точки (⋮) → Импорт из буфера\n\n"
    "Если ссылка не открылась по нажатию, скопируйте её (долгое нажатие на ссылку → «Копировать») "
    "и вставьте в «Импорт из буфера», либо откройте ссылку на устройстве с установленным Happ."
)


def routing_message_html() -> str:
    """Второе сообщение: ссылка happ:// в виде копируемого текста + шаги в Happ.

    Примечание: Telegram в режиме HTML не делает кликабельным happ:// в теге <a> (только http/https и др.).
    Полная ссылка выводится в моноширинном блоке — её можно скопировать одним нажатием (в приложении Telegram).
    """
    url_in_code = html_module.escape(RU_ROUTING_HAPP_IMPORT)
    body = html_module.escape(ROUTING_UI_STEPS_RU)
    return (
        "<b>Российские сайты без отключения VPN</b>\n\n"
        "Чтобы не выключать сервис для доступа к российским сайтам, добавьте профиль маршрутизации.\n\n"
        "<b>Ссылка с настройками RU</b> — скопируйте строку ниже целиком "
        "(нажмите на блок с текстом → «Копировать»):\n\n"
        f"<code>{url_in_code}</code>\n\n"
        f"{body}"
    )


def text_windows_part1() -> str:
    return (
        "Windows — Happ\n\n"
        "1) Установите приложение:\n"
        f"{HAPP_WINDOWS_SETUP_URL}\n\n"
        "2) Скопируйте ссылку подключения (VLESS), которую бот прислал выше.\n"
        "3) Откройте Happ и вставьте скопированную ссылку, чтобы добавить подключение "
        "(через «Добавить из буфера» / импорт ссылки — как предлагает приложение)."
    )


def text_linux_part1() -> str:
    return (
        "Linux — Happ\n\n"
        "1) Установите пакет (.deb):\n"
        f"{HAPP_LINUX_DEB_URL}\n"
        "(например: sudo apt install ./Happ.linux.x64.deb или через установщик).\n\n"
        "2) Скопируйте ссылку подключения (VLESS), которую бот прислал выше.\n"
        "3) Запустите Happ и вставьте скопированную ссылку, чтобы добавить подключение."
    )


def text_mac_part1() -> str:
    return (
        "macOS — Happ\n\n"
        "1) Установите приложение из App Store:\n"
        f"{HAPP_MAC_APP_STORE_URL}\n\n"
        "2) Скопируйте ссылку подключения (VLESS), которую бот прислал выше.\n"
        "3) Откройте Happ и вставьте скопированную ссылку, чтобы добавить подключение."
    )


def text_ios_part1() -> str:
    return (
        "iOS — Happ\n\n"
        "1) Установите приложение из App Store:\n"
        f"{HAPP_IOS_APP_STORE_URL}\n\n"
        "2) Скопируйте ссылку подключения (VLESS), которую бот прислал выше.\n"
        "3) Откройте Happ и вставьте скопированную ссылку, чтобы добавить подключение."
    )


def text_android_part1() -> str:
    return (
        "Android — Happ\n\n"
        "1) Установите приложение из Google Play:\n"
        f"{HAPP_ANDROID_PLAY_URL}\n\n"
        "2) Скопируйте ссылку подключения (VLESS), которую бот прислал выше.\n"
        "3) Откройте Happ и вставьте скопированную ссылку, чтобы добавить подключение."
    )


GUIDE_PART1_BY_PLATFORM = {
    "win": text_windows_part1,
    "linux": text_linux_part1,
    "mac": text_mac_part1,
    "ios": text_ios_part1,
    "android": text_android_part1,
}
