# Запуск бота на VPS: системный systemd + права для `vpn-bot`

Сервис ставится **в систему** (`/etc/systemd/system/`) — устанавливать и включать нужно **от root** (SSH под `root` или `su -`, либо `sudo`, если пакет `sudo` установлен).

Процесс бота по-прежнему работает от пользователя **`vpn-bot`** (см. `User=` в `vpn-bot.service`) — так безопаснее, чем запуск от root.

Пользователь **`vpn-bot`** после настройки `sudoers` может **без пароля** только перезапускать/останавливать этот сервис командой `sudo systemctl …` (для этого на сервере должен быть пакет **`sudo`**: `apt install -y sudo` от root).

---

## Пути (как у вас на сервере)

| Что | Путь |
|-----|------|
| Пользователь ОС | `vpn-bot` |
| Код (корень репозитория) | `/home/vpn-bot/apps/vpn-bot` |
| Виртуальное окружение | `/home/vpn-bot/apps/vpn-bot/.venv` |
| Конфиг | `/home/vpn-bot/apps/vpn-bot/.env` |
| Юнит systemd | `/etc/systemd/system/vpn-bot.service` |

---

## 1. Пользователь `vpn-bot` (от root)

```bash
adduser --disabled-password --gecos "" vpn-bot
```

(Если уже есть — пропустите.)

---

## 2. Код и venv (от root, команды от имени `vpn-bot`)

```bash
su - vpn-bot -s /bin/bash -c 'mkdir -p ~/apps && cd ~/apps && git clone https://github.com/pr0gh0st/AccessGrantedRU_VPN_Bot.git vpn-bot'
```

Обновление:

```bash
su - vpn-bot -s /bin/bash -c 'cd ~/apps/vpn-bot && git pull'
```

Venv и зависимости:

```bash
su - vpn-bot -s /bin/bash -c 'cd ~/apps/vpn-bot && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt'
```

`.env` в `/home/vpn-bot/apps/vpn-bot/.env`:

```bash
chown vpn-bot:vpn-bot /home/vpn-bot/apps/vpn-bot/.env
chmod 600 /home/vpn-bot/apps/vpn-bot/.env
```

Проверка вручную:

```bash
su - vpn-bot -s /bin/bash -c 'cd ~/apps/vpn-bot && .venv/bin/python -m src.app'
```

---

## 3. Системный сервис (от root)

```bash
cp /home/vpn-bot/apps/vpn-bot/deploy/vpn-bot.service /etc/systemd/system/vpn-bot.service
systemctl daemon-reload
systemctl enable --now vpn-bot.service
systemctl status vpn-bot.service
```

Логи:

```bash
journalctl -u vpn-bot.service -f
```

---

## 4. Пакет `sudo` и права для `vpn-bot`

Чтобы пользователь `vpn-bot` мог выполнять `sudo systemctl …` **без пароля** только для этого юнита:

```bash
apt install -y sudo
```

Проверьте путь к `systemctl` (`command -v systemctl`). В `deploy/vpn-bot.sudoers` должны совпадать пути (часто `/usr/bin/systemctl`).

```bash
cp /home/vpn-bot/apps/vpn-bot/deploy/vpn-bot.sudoers /etc/sudoers.d/vpn-bot
chmod 440 /etc/sudoers.d/vpn-bot
visudo -cf /etc/sudoers.d/vpn-bot
```

Ожидается: `parsed OK`.

---

## 5. Команды под пользователем `vpn-bot`

```bash
sudo systemctl status vpn-bot.service
sudo systemctl stop vpn-bot.service
sudo systemctl start vpn-bot.service
sudo systemctl restart vpn-bot.service
```

Типичное обновление:

```bash
cd ~/apps/vpn-bot && git pull && sudo systemctl restart vpn-bot.service
```

---

## 6. Другие пути на диске

Правьте `/etc/systemd/system/vpn-bot.service` (`WorkingDirectory`, `ExecStart`), затем от root:

```bash
systemctl daemon-reload
systemctl restart vpn-bot.service
```
