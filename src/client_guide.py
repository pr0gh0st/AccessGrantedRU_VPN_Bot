"""Ссылки и тексты помощи по подключению Happ / VLESS (без секретов панели)."""

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

# Импорт RU-маршрутов: вставить в «Импорт из буфера» (одинаково для всех платформ Happ)
RU_ROUTING_HAPP_IMPORT = (
    "happ://routing/add/eyJSb3V0ZU9yZGVyIjoiYmxvY2stZGlyZWN0LXByb3h5IiwiRG9tZXN0aWNETlNUeXBlIjoiRG9VIiwiUmVtb3RlRE5TVHlwZSI6IkRvVSIsIkRuc0hvc3RzIjp7fSwiUHJveHlTaXRlcyI6W10sIkRvbWVzdGljRE5TRG9tYWluIjoiaHR0cHM6XC9cL2Rucy5nb29nbGVcL2Rucy1xdWVyeSIsIkdlb2lwVXJsIjoiaHR0cHM6XC9cL2dpdGh1Yi5jb21cL0xveWFsc29sZGllclwvdjJyYXktcnVsZXMtZGF0XC9yZWxlYXNlc1wvbGF0ZXN0XC9kb3dubG9hZFwvZ2VvaXAuZGF0IiwiQmxvY2tJcCI6W10sIlJlbW90ZUROU0RvbWFpbiI6Imh0dHBzOlwvXC9jbG91ZGZsYXJlLWRucy5jb21cL2Rucy1xdWVyeSIsIkRpcmVjdFNpdGVzIjpbImdlb3NpdGU6Y2F0ZWdvcnktcnUiXSwiUHJveHlJcCI6W10sIlVzZUNodW5rRmlsZXMiOnRydWUsIkdsb2JhbFByb3h5Ijp0cnVlLCJEb21haW5TdHJhdGVneSI6IklQSWZOb25NYXRjaCIsIkxhc3RVcGRhdGVkIjoxNzc1NjQ0NzQ0LCJEaXJlY3RJcCI6WyIxMC4wLjAuMFwvOCIsIjEwMC42NC4wLjBcLzEwIiwiMTcyLjE2LjAuMFwvMTIiLCIxOTIuMTY4LjAuMFwvMTYiLCIxNjkuMjU0LjAuMFwvMTYiLCIyMjQuMC4wLjBcLzQiLCIyNTUuMjU1LjI1NS4yNTUiLCJnZW9pcDpydSJdLCJCbG9ja1NpdGVzIjpbXSwiUmVtb3RlRE5TSXAiOiIxLjEuMS4xIiwiRG9tZXN0aWNETlNJcCI6IjguOC44LjgiLCJHZW9zaXRlVXJsIjoiaHR0cHM6XC9cL2dpdGh1Yi5jb21cL0xveWFsc29sZGllclwvdjJyYXktcnVsZXMtZGF0XC9yZWxlYXNlc1wvbGF0ZXN0XC9kb3dubG9hZFwvZ2Vvc2l0ZS5kYXQiLCJOYW1lIjoiUlVub3RWUE4iLCJGYWtlRG5zIjpmYWxzZX0="
)

# Общий блок: куда нажать в Happ для импорта готовых правил RU
ROUTING_UI_STEPS_RU = (
    "Добавление RU-маршрутов (обход VPN для российских ресурсов):\n"
    "Настройки → Правила маршрутизации → три точки (⋮) → Импорт из буфера\n\n"
    "Скопируйте строку ниже целиком, затем вставьте её в импорт из буфера "
    "(или откройте ссылку на устройстве — Happ подхватит профиль маршрутов, если поддерживается)."
)


def text_windows_guide() -> str:
    return (
        "Windows — Happ\n\n"
        f"Скачайте установщик:\n{HAPP_WINDOWS_SETUP_URL}\n\n"
        f"{ROUTING_UI_STEPS_RU}"
    )


def text_linux_guide() -> str:
    return (
        "Linux — Happ\n\n"
        f"Скачайте пакет (.deb):\n{HAPP_LINUX_DEB_URL}\n\n"
        "Установите пакет (например: sudo apt install ./Happ.linux.x64.deb или через установщик).\n"
        "Запустите Happ и добавьте вашу VLESS-ссылку в подключения.\n\n"
        f"{ROUTING_UI_STEPS_RU}"
    )


def text_mac_guide() -> str:
    return (
        "macOS — Happ\n\n"
        f"Установите приложение из App Store:\n{HAPP_MAC_APP_STORE_URL}\n\n"
        "Откройте Happ, добавьте подключение по вашей VLESS-ссылке.\n\n"
        f"{ROUTING_UI_STEPS_RU}"
    )


def text_ios_guide() -> str:
    return (
        "iOS — Happ\n\n"
        f"Установите приложение из App Store:\n{HAPP_IOS_APP_STORE_URL}\n\n"
        "Откройте Happ, добавьте подключение по вашей VLESS-ссылке.\n\n"
        f"{ROUTING_UI_STEPS_RU}"
    )


def text_android_guide() -> str:
    return (
        "Android — Happ\n\n"
        f"Установите приложение из Google Play:\n{HAPP_ANDROID_PLAY_URL}\n\n"
        "Откройте Happ, добавьте подключение по вашей VLESS-ссылке.\n\n"
        f"{ROUTING_UI_STEPS_RU}"
    )


GUIDE_TEXT_BY_PLATFORM = {
    "win": text_windows_guide,
    "linux": text_linux_guide,
    "mac": text_mac_guide,
    "ios": text_ios_guide,
    "android": text_android_guide,
}
