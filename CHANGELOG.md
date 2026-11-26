# Changelog

## 2026-11-20
- E4.1: таблица `superadmins` (платформа + uid), миграция `SUPERADMIN_ID` из config в БД, функции `is_superadmin_db` и `get_admin_role_by_platform`, API роутер `routers/admin_bots.py` (GET/POST/PATCH/DELETE ботов), платформо-агностичная логика выбора организации в обоих ботах (MAX/VK).

## 2026-02-05
- E4.0–E4.1: канал VK (`core/channels/vk.py`), приём Callback API (`core/webhook_adapters/vk.py`, `routers/webhook_vk.py`), секрет и confirmation берутся из `bots`, роутер подключён в `app.py`, добавлен `location` в `nginx.conf.snippet`, привязка бота скриптом `vk_setup_bot.py`.

## 2026-02-05
- E3, шаг 3: `core/broadcasts.py` переведён на общую абстракцию каналов (картинки через канал клиента, `phone:...` вне сегментов, новый статус `skipped` для клиентов без канала).

## 2026-02-05
- E3, шаг 2: функции над `client_identities`/`bots`, выбор канала по паспортам в `get_channel_for_client`, настройки `channel_default`/`channel_duplicate` и селектор канала в настройках админки.

## 2026-02-05
- E3, шаг 1: в `storage/db.py` добавлены таблицы `client_identities` (паспорта каналов) и `bots`, разовая идемпотентная миграция `clients.user_id` → identity `max`.
