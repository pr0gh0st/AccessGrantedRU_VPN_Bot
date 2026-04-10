# Запуск бота на VPS (systemd + пользователь `vpn-bot`)

Инструкция с учётом **вашего текущего размещения**:

| Что | Путь |
|-----|------|
| Пользователь ОС | `vpn-bot` |
| Код (корень репозитория) | `/home/vpn-bot/apps/vpn-bot` |
| Виртуальное окружение | `/home/vpn-bot/apps/vpn-bot/.venv` |
| Конфиг | `/home/vpn-bot/apps/vpn-bot/.env` |
| Юнит systemd | `vpn-bot.service` |

---

## 1. Если пользователя ещё нет

```bash
sudo adduser --disabled-password --gecos "" vpn-bot
```

(Если пользователь уже создан — шаг пропустите.)

---

## 2. Код и venv (как у вас)

Под `vpn-bot`:

```bash
sudo -u vpn-bot -H bash -lc 'mkdir -p ~/apps && cd ~/apps && git clone https://github.com/pr0gh0st/AccessGrantedRU_VPN_Bot.git vpn-bot'
```

Если каталог `vpn-bot` уже есть — только обновление:

```bash
sudo -u vpn-bot -H bash -lc 'cd ~/apps/vpn-bot && git pull'
```

Venv и зависимости:

```bash
sudo -u vpn-bot -H bash -lc 'cd ~/apps/vpn-bot && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt'
```

Файл `.env` в корне репозитория (`/home/vpn-bot/apps/vpn-bot/.env`), права:

```bash
sudo chown vpn-bot:vpn-bot /home/vpn-bot/apps/vpn-bot/.env
sudo chmod 600 /home/vpn-bot/apps/vpn-bot/.env
```

---

## 3. Установка сервиса systemd

Из корня репозитория на сервере:

```bash
sudo cp /home/vpn-bot/apps/vpn-bot/deploy/vpn-bot.service /etc/systemd/system/vpn-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now vpn-bot.service
sudo systemctl status vpn-bot.service
```

Логи:

```bash
journalctl -u vpn-bot.service -f
```

Проверка руками (без systemd), от имени `vpn-bot`:

```bash
sudo -u vpn-bot -H bash -lc 'cd ~/apps/vpn-bot && .venv/bin/python -m src.app'
```

---

## 4. Права `vpn-bot` на start / stop / restart

Файл `deploy/vpn-bot.sudoers` разрешает **только** управление этим сервисом без пароля.

Проверьте путь к `systemctl`:

```bash
command -v systemctl
```

Если вывод не `/usr/bin/systemctl` — отредактируйте строку в `deploy/vpn-bot.sudoers`, подставив свой путь.

Установка:

```bash
sudo cp /home/vpn-bot/apps/vpn-bot/deploy/vpn-bot.sudoers /etc/sudoers.d/vpn-bot
sudo chmod 440 /etc/sudoers.d/vpn-bot
sudo visudo -cf /etc/sudoers.d/vpn-bot
```

Должно быть: `parsed OK`.

---

## 5. Команды для пользователя `vpn-bot`

```bash
sudo systemctl status vpn-bot.service
sudo systemctl stop vpn-bot.service
sudo systemctl start vpn-bot.service
sudo systemctl restart vpn-bot.service
```

Обновление кода и перезапуск (типичный сценарий):

```bash
cd ~/apps/vpn-bot
git pull
sudo systemctl restart vpn-bot.service
```

---

## 6. Если пути на сервере другие

Отредактируйте `/etc/systemd/system/vpn-bot.service` (`WorkingDirectory`, `ExecStart`), затем:

```bash
sudo systemctl daemon-reload
sudo systemctl restart vpn-bot.service
```
