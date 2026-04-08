## Telegram VPN бот для 3X-UI (aiogram 3 + SQLAlchemy 2)

Production-ready каркас бота для продажи и управления VPN-подписками через панель **3X-UI**.

### Что уже реализовано

- **Конфиг через `.env`** (Pydantic Settings)
- **SQLite + SQLAlchemy ORM (async)**:
  - модели: `User`, `StaticProfile`, `PaymentLog`, `AdminBroadcastLog`
  - набор функций БД из ТЗ (создание пользователя, trial, продление, профили, платежи, трафик и т.д.)
- **3X-UI API адаптер** `XUIAPI`:
  - login (учитывает кастомный путь `/<CUSTOM_PATH>/login`)
  - get inbound / add client / del client / traffic
  - fallback на разные форматы `settings` (объект vs JSON-строка), т.к. версии 3X-UI могут отличаться
- **Базовые сценарии Telegram**:
  - `/start`, `/menu`, `/profile`, `/myvpn`, `/traffic`, `/help`
  - trial (однократно) + создание VLESS клиента в 3X-UI + сохранение в БД
  - создание/удаление VLESS профиля, подтверждение опасного действия
  - запрос трафика из 3X-UI и сохранение статистики в БД

### Что будет добавлено следующими этапами

- Telegram Payments (`/buy`, invoice, `pre_checkout_query`, `successful_payment`) + `PaymentLog` + продление подписки
- Админ-панель (пользователи, поиск, +/- дни, рассылка, статические профили, платежи)
- Фоновая задача (часовой джоб: уведомления за 24ч, деактивация истекших, удаление профиля в 3X-UI)

---

## Установка (Windows 10/11, PowerShell)

### 0) Требования

- **Python 3.10+**
- Git (опционально, но желательно)
- Доступ к вашей панели **3X-UI** по HTTP(S)

### 1) Клонирование репозитория

Если вы уже в папке проекта (как сейчас), пропустите.

```bash
git clone <YOUR_REPO_URL>
cd <YOUR_REPO_DIR>
```

### 2) Создание виртуального окружения

Из корня проекта:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

Если у вас нет `py`, используйте установленный `python` (но важно чтобы это был Python 3.10+).

### 3) Установка зависимостей

```powershell
pip install -r requirements.txt
```

### 4) Создание `.env`

Файл `.env` должен лежать **в корне репозитория** (на уровне `README.md`).

Скопируйте пример:

```powershell
Copy-Item .\src\.env.example .\.env
```

Теперь откройте `.env` и заполните значения.

---

## Что важно заполнить в `.env` (обязательно)

### Telegram

- **`BOT_TOKEN`**: токен вашего бота от `@BotFather`
- **`PAYMENT_TOKEN`**: токен провайдера платежей (будет использоваться на следующем этапе)
- **`ADMINS`**: список Telegram ID админов через запятую, например `123,456`

### 3X-UI (критично)

В вашем случае панель живёт по:
`http://<IP>:<PORT>/<CUSTOM_PATH>/login`

поэтому:

- **`XUI_API_URL`** = `http://<IP>:<PORT>` (ВАЖНО: **без** `/<CUSTOM_PATH>`)
- **`XUI_BASE_PATH`** = `<CUSTOM_PATH>` (ВАЖНО: **без** слэшей)

Дополнительно:
- **`XUI_USERNAME`**, **`XUI_PASSWORD`**: логин/пароль панели
- **`INBOUND_ID`**: ID inbound’а в 3X-UI, к которому добавляем клиентов
- **`XUI_HOST`**: хост для VLESS ссылки (обычно домен или IP, который используют клиенты)

### Reality параметры для ссылки VLESS

- `REALITY_PUBLIC_KEY`
- `REALITY_FINGERPRINT`
- `REALITY_SNI`
- `REALITY_SHORT_ID`
- `REALITY_SPIDER_X`

### Trial и цены

- `TRIAL_DAYS` — trial в днях
- `PRICE_1_MONTH`, `PRICE_3_MONTHS`, `PRICE_6_MONTHS`, `PRICE_12_MONTHS` — цены в **минорных единицах** валюты (например, центы)
- `CURRENCY` — валюта (`USD`, `RUB`, `EUR` и т.п.)

---

## Запуск бота

Из корня проекта, с активированным venv:

```powershell
python -m src.app
```

Что произойдет при старте:
- конфиг проверит обязательные переменные
- создаст/обновит таблицы SQLite
- запустит polling

### Где лежит база данных

По умолчанию используется SQLite файл `users.db` в корне репозитория.
Он **не коммитится** в git (см. `.gitignore`) и создается при первом запуске автоматически.

Если хотите изменить путь, используйте переменную:
- `DATABASE_URL` (по умолчанию `sqlite+aiosqlite:///users.db`)

---

## Структура проекта

```
.
├── src
│   ├── .env.example
│   ├── app.py
│   ├── config.py
│   ├── database.py
│   ├── functions.py
│   ├── handlers.py
│   ├── keyboards.py
│   ├── services.py
│   └── utils.py
├── README.md
├── requirements.txt
└── users.db   (создаётся при запуске)
```

---

## Важные замечания по 3X-UI API

3X-UI иногда отличается по:
- формату полей `settings` (объект vs JSON-строка)
- форме ответа некоторых endpoint’ов

В `src/functions.py` эти места вынесены в адаптер и сделаны fallback’и.
Если в вашей версии панель ведёт себя иначе, правки делаются **только** в адаптере `XUIAPI`.

