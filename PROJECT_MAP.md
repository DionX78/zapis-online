# PROJECT MAP — max_booking_bot

*Сгенерировано: 2026-11-27 08:24*
*Скрипт: `tools/gen_map.py`. Файл автогенерируемый — не редактировать вручную.*

## Дерево
```
.env
.gitignore
CHANGELOG.md
PLAN.md
PROJECT_MAP.md
PROJECT_MAP_SHORT.md
app.py
backup_db.sh
booking.db
config.py
deploy.sh
init_project.py
max-bot.service
nginx.conf.snippet
package-lock.json
register_webhook.py
requirements.txt
scan_project.py
seed.py
core/
  __init__.py
  analytics_export.py
  auth.py
  booking.py
  broadcasts.py
  client_exports.py
  dispatcher.py
  geo.py
  ics.py
  max_client.py
  merge.py
  messaging.py
  notify.py
  notify_ics.py
  reminders.py
  schedule_gateway.py
  updates.py
  uploads.py
  waitlist.py
  channels/
    __init__.py
    base.py
    max.py
    registry.py
    vk.py
    vk_text.py
  webhook_adapters/
    max.py
    vk.py
handlers/
  __init__.py
  admin.py
  booking.py
  client_confirm_callbacks.py
  merge_callbacks.py
  reminder_callbacks.py
  report_callbacks.py
  request_callbacks.py
  review_callbacks.py
  start.py
  superadmin_callbacks.py
  unsub_callbacks.py
  visit_callbacks.py
mini/
  .env.example
  booking.db
  index.html
  package-lock.json
  package.json
  vite.config.js
  src/
    App.jsx
    ClientApp.jsx
    api.js
    main.jsx
    theme.css
    admin/
      AdminApp.jsx
      AnalyticsPage.jsx
      AuditLogPage.jsx
      BlockedUsersPage.jsx
      BroadcastsPage.jsx
      ChannelsPage.jsx
      ClientCardModal.jsx
      ClientMessageModal.jsx
      ClientPrivacyModal.jsx
      ClientsPage.jsx
      CreateRequestModal.jsx
      DashboardPage.jsx
      DirectoriesPage.jsx
      DoctorScheduleModal.jsx
      DoctorServicesModal.jsx
      DoctorStatsModal.jsx
      EditRequestModal.jsx
      MarkVisitModal.jsx
      MoveRequestModal.jsx
      RequestsPage.jsx
      ReviewsPage.jsx
      SchedulePage.jsx
      SettingsPage.jsx
      VisitDetailsModal.jsx
      WaitlistPage.jsx
      adminApi.js
    components/
      CalendarGrid.jsx
      DoctorPicker.jsx
      PhoneForm.jsx
      ServiceList.jsx
      Success.jsx
      TimeGrid.jsx
      WaitlistForm.jsx
      WaitlistPage.jsx
routers/
  __init__.py
  admin_bots.py
  admin_broadcasts.py
  admin_core.py
  admin_directories.py
  admin_requests.py
  admin_reviews.py
  admin_settings.py
  admin_uploads.py
  mini_app.py
  webhook.py
  webhook_vk.py
storage/
  __init__.py
  db.py
tools/
  gen_map.py
```

## Файлы

### `.env` (5 стр.)

### `.gitignore` (14 стр.)

### `CHANGELOG.md` (16 стр.)

### `PLAN.md` (1219 стр.)

### `PROJECT_MAP.md` (1308 стр.)

### `PROJECT_MAP_SHORT.md` (137 стр.)

### `app.py` (74 стр.)
импорты: `config`, `core`, `fastapi`, `routers`, `storage`, `truststore`
- ƒ async def lifespan(app: FastAPI)

### `backup_db.sh` (26 стр.)
_пусто / без явных объявлений_

### `booking.db` (1203 стр.)

### `config.py` (69 стр.)
импорты: `dotenv`
- ƒ def is_superadmin(uid)

### `deploy.sh` (151 стр.)
_пусто / без явных объявлений_

### `init_project.py` (696 стр.)
- ƒ def write(rel, content)
- ƒ def main()

### `max-bot.service` (15 стр.)

### `nginx.conf.snippet` (22 стр.)

### `package-lock.json` (6 стр.)

### `register_webhook.py` (36 стр.)
импорты: `config`, `httpx`, `truststore`
_пусто / без явных объявлений_

### `requirements.txt` (10 стр.)

### `scan_project.py` (273 стр.)
- ƒ def _is_project_excluded_path(rel_path) — Проверяет, попадает ли относительный путь под проектные исключения.
- ƒ def _is_project_excluded_file(filename) — Проверяет имя файла по проектным исключениям.
- ƒ def make_output_filename(root_dir: str) -> str
- ƒ def safe_read_bytes(file_path)
- ƒ def decode_bytes(content_bytes)
- ƒ def _filter_dirnames(dirnames, rel_dir) — Универсальная + проектная фильтрация папок.
- ƒ def scan_project()

### `seed.py` (75 стр.)
импорты: `storage`
_пусто / без явных объявлений_

### `core/__init__.py` (0 стр.)
_пусто / без явных объявлений_

### `core/analytics_export.py` (582 стр.)
импорты: `config`, `core`, `openpyxl`, `reportlab`, `storage`
- ƒ def analytics_export_filename(prefix, fmt, date_from, date_to)
- ƒ def build_analytics_csv(data)
- ƒ def build_analytics_xlsx(data)
- ƒ def build_analytics_pdf(data)
- ƒ async def generate_and_send_analytics(org_id: int, admin_uid: int, date_from: str, date_to: str, fmt: str, branch_id: int | None, doctor_id: int | None, caption_prefix: str) -> dict — Генерирует аналитику за период, отправляет в чат admin_uid.

### `core/auth.py` (176 стр.)
импорты: `config`, `fastapi`, `storage`
- 🏛 **AdminCtx**
- ƒ def validate_webapp_data(init_data: str, max_age_seconds: int)
- ƒ def get_user_from_request(request: Request)
- ƒ def get_uid_from_user(user)
- ƒ async def require_user(request: Request) -> dict
- ƒ async def admin_ctx(request: Request) -> AdminCtx
- ƒ async def superadmin_ctx(ctx: AdminCtx) -> AdminCtx
- ƒ async def org_ctx(ctx: AdminCtx) -> AdminCtx
- ƒ def require_branch(ctx: AdminCtx, branch_id: int)
- ƒ def require_doctor(ctx: AdminCtx, doctor_id: int)
- ƒ def require_service(ctx: AdminCtx, service_id: str)

### `core/booking.py` (682 стр.)
импорты: `core`, `storage`
- 🏛 **BookingContext**
- 🏛 **BookingResult**
- ƒ def _valid_birth_date(value)
- ƒ async def _try_send_welcome_first(ctx: BookingContext, request_id: int) — Если это первая запись клиента в org — отправить сценарий welcome_first.
- ƒ def validate_booking(ctx: BookingContext) — Все проверки. Возвращает (ok, error_code, error_msg, info).
- ƒ async def create_booking_unified(ctx: BookingContext) -> BookingResult
- 🏛 **MoveResult**
- ƒ async def move_booking_unified(request_id: int, new_slot_id: int, via: str) -> MoveResult — Атомарный перенос активной записи на новый слот.

### `core/broadcasts.py` (880 стр.)
импорты: `config`, `core`, `storage`
- ƒ async def refresh_image_token(upload_id, channel, user_id) — Перезагружает файл с диска в канал, обновляет token в БД.
- ƒ async def _send_with_refresh(user_id, text, image_id, buttons, fmt, org_id) — Отправляет сообщение с картинкой через канал клиента (не MAX напрямую).
- ƒ def get_clients_for_segment(org_id: int, segment: dict) -> list[str]
- ƒ def create_broadcast(org_id, text, segment, created_by, image_id, scheduled_at, status)
- ƒ def get_broadcast(bid)
- ƒ def list_broadcasts(org_id, limit)
- ƒ def start_broadcast(bid, total_recipients)
- ƒ def cancel_broadcast(bid)
- ƒ def delete_broadcast(bid)
- ƒ def get_pending_broadcasts()
- ƒ def get_next_pending_send(broadcast_id)
- ƒ def mark_send(broadcast_id, user_id, status, error)
- ƒ def finalize_broadcast_if_done(broadcast_id)
- ƒ def prepare_broadcast_sends(bid, user_ids)
- ƒ def get_broadcast_sends(bid, limit)
- ƒ def update_broadcast_draft(bid, text, segment, image_id)
- ƒ def start_draft_broadcast(bid)
- ƒ def duplicate_broadcast(bid, created_by) — Создаёт новый draft — копию с тем же текстом, сегментом, картинкой.
- ƒ async def _check_manual_broadcasts()
- ƒ async def _check_scheduled_broadcasts() — Раз в 60 сек проверяет запланированные рассылки (лёгкий SELECT).
- ƒ def format_auto_broadcast_text(template, user_id, org_id, request_id) — Подставляет переменные в текст сценария.
- ƒ async def _check_auto_broadcasts()
- ƒ async def run_broadcast_worker()

### `core/client_exports.py` (657 стр.)
импорты: `openpyxl`, `reportlab`, `storage`
- ƒ def build_client_export_csv(data, client)
- ƒ def build_client_export_xlsx(data, client, for_client)
- ƒ def build_client_export_pdf(data, client, for_client)

### `core/dispatcher.py` (130 стр.)
импорты: `config`, `core`, `handlers`
- ƒ async def route(update: Update) — Маршрутизация одного Update. Не зависит от платформы.
- ƒ async def _handle_message(uid, text, platform)
- ƒ async def _handle_callback(uid, payload, message_id, platform)
- ƒ async def route_update(data: dict) — Совместимая обёртка: сырой dict → parse → route.

### `core/geo.py` (65 стр.)
импорты: `config`, `storage`
- ƒ def yandex_maps_link(address: str) -> str — Ссылка на Яндекс.Карты по текстовому адресу.
- ƒ def gis_maps_link(address: str) -> str — Ссылка на 2ГИС по текстовому адресу.
- ƒ def _resolve_provider(org_id, provider)
- ƒ def route_lines(address: str, org_id, provider: str | None) -> str — Markdown-фрагмент для сообщения бота:

### `core/ics.py` (107 стр.)
импорты: `storage`
- ƒ def _escape(value: str) -> str — Экранирование строк по RFC 5545.
- ƒ def _to_utc(date_str: str, time_str: str, tz_name: str) — local (naive) -> aware UTC.
- ƒ def _fmt_dt(dt: datetime) -> str
- ƒ def build_ics(request_id: int, org_id: int, service_name: str, scheduled_at: str, duration_min: int, address: str, doctor: str, prep: str, uid_domain: str) -> str — Возвращает текст .ics-файла для заявки.

### `core/max_client.py` (414 стр.)
импорты: `config`, `httpx`, `truststore`
- 🏛 **MaxUserBlocked** — Клиент заблокировал бота (403/404). Воркеры ловят это исключение
- ƒ async def send_message(user_id: int, text: str, buttons: list, fmt: str, max_retries: int) — Отправляет сообщение через MAX API.
- ƒ async def send_message_with_image(user_id: int, text: str, image_token: str, buttons: list, fmt: str, max_retries: int) — Отправляет сообщение с картинкой.
- ƒ def _extract_token(data: dict) -> str | None — Устойчивый парсер ответа MAX при загрузке файла.
- ƒ async def upload_file(content, filename: str, mime: str, upload_type: str, max_retries: int) -> str — Загружает файл в MAX, возвращает token для использования в attachment.
- ƒ async def send_message_with_file(user_id: int, text: str, file_token: str, buttons: list, fmt: str, max_retries: int) — Отправляет сообщение с файлом-вложением (attachment type=file).
- ƒ async def edit_message(message_id: str, text: str, buttons: list, fmt: str) — Редактирует сообщение.
- ƒ async def delete_message(message_id: str) — Удаляет сообщение.
- ƒ async def set_commands(commands: list) — Регистрирует команды бота.
- ƒ async def get_me() — Возвращает информацию о боте.

### `core/merge.py` (289 стр.)
импорты: `core`, `storage`
- ƒ def _canon(phone)
- ƒ def _ensure_table(conn)
- ƒ def find_other_clients_by_phone(org_id, user_id, phone) — Реальные клиенты (не phone:...) с тем же телефоном, кроме самого себя.
- ƒ def create_pending_merges(org_id, user_id, phone) — Заявки на склейку с каждым реальным клиентом с тем же телефоном.
- ƒ def get_pending_merge(merge_id)
- ƒ def confirm_merge(merge_id, which)
- ƒ def set_merge_status(merge_id, status)
- ƒ def finalize_merge(keep_uid, gone_uid) — Склейка: сначала дозаполняем пустые поля keep данными gone,
- ƒ def _merge_buttons(merge_id)
- ƒ async def _send_merge_request(uid, text, merge_id)
- ƒ async def _send_simple(uid, text)
- ƒ async def maybe_queue_merge(org_id, user_id, phone) — Вызывается после успешной записи: ищет профили с тем же телефоном
- ƒ async def handle_response(merge_id, uid, yes)

### `core/messaging.py` (383 стр.)
импорты: `config`, `core`, `httpx`, `storage`
- ƒ def _should_duplicate(duplicate, org_id) -> bool — Дублировать ли отправку во все каналы клиента.
- ƒ async def send_to_client(user_id, text, buttons, fmt, org_id, duplicate) — Отправляет сообщение клиенту. Возвращает (status, error).
- ƒ def _client_org_id(uid_str)
- ƒ async def _send_raw_multichannel(uid_str, org_id, duplicate, send_one)
- ƒ async def send_to_client_raw(user_id, text, buttons, fmt, org_id, duplicate) — Текст. Бросает UserBlocked/ChannelError. duplicate — во все каналы клиента.
- ƒ def _stored_image_bytes(token) — Байты картинки по токену: blob в БД или файл на диске.
- ƒ def _vk_token()
- ƒ def _vk_api()
- ƒ def _vk_version()
- ƒ async def _vk_upload_photo(content, mime) — Загружает картинку в VK, возвращает attachment 'photo{id}_{id}'.
- ƒ async def send_to_client_with_image_raw(user_id, text, image_token, buttons, fmt, org_id, duplicate) — Сообщение с картинкой. МАХ получает свой токен, ВК — своё вложение.
- ƒ async def send_to_client_with_file_raw(user_id, text, file_token, buttons, fmt, org_id, duplicate) — Сообщение с файлом (.ics и т.п.). duplicate/org_id — как выше.
- ƒ async def edit_message_for_client(user_id, message_id, text, buttons, fmt) — Редактирует сообщение. Возвращает dict | None. Не бросает.
- ƒ async def delete_message_for_client(user_id, message_id) — Удаляет сообщение. Возвращает dict | None. Не бросает.
- ƒ async def upload_file_for_client(user_id, content, filename: str, mime: str, upload_type: str) -> str — Загружает файл в канал клиента. Возвращает token или бросает ChannelError.

### `core/notify.py` (32 стр.)
импорты: `config`, `core`, `storage`
- ƒ async def notify_admins(text: str, org_id, buttons) — Если org_id задан — шлём админам этой организации.

### `core/notify_ics.py` (64 стр.)
импорты: `core`, `storage`
- ƒ async def send_confirmation_with_ics(user_id, text, request_id, org_id, service_id, service_name, scheduled_at, address, doctor, prep) — Отправляет сообщение с .ics-вложением.

### `core/reminders.py` (668 стр.)
импорты: `config`, `core`, `storage`
- ƒ def _is_phone_only(user_id) -> bool
- ƒ def _parse_sched(sched_str)
- ƒ def _is_quiet_hours(now_local, start_hour, end_hour) — Проверка «тихих часов». Границы можно передать явно
- ƒ async def _send_reminder(request_id, kind, attempts_used, now_local)
- ƒ def _get_created_at(request_id)
- ƒ async def _check_reminders()
- ƒ async def _ask_client_confirm(request_id, attempts_used)
- ƒ async def _check_client_confirm()
- ƒ async def _check_client_timeout()
- ƒ async def _check_review_requests() — Отправляет запрос на отзыв клиентам через N часов после done-визита.
- ƒ def _evening_summary_buttons(org_id, today_str)
- ƒ async def _send_evening_summary(org_id, today_str)
- ƒ async def _check_evening_summaries()
- ƒ async def _extend_schedules_horizon() — Раз в сутки продлевает горизонт автогенерированных слотов для всех организаций.
- ƒ async def _cleanup_temp_exports() — Удаляет временные файлы экспорта (csv/xlsx/pdf):
- ƒ async def _daily_housekeeping() — Ежедневные задачи по каждой организации:
- ƒ async def run_reminder_worker()
- ƒ async def run_supervised(name: str, worker_fn) — Обёртка для фоновых воркеров: перезапускает при падении.

### `core/schedule_gateway.py` (39 стр.)
импорты: `config`, `storage`
- 🏛 **ScheduleGateway**
-   · def get_dates(self, org_id, limit_days)
-   · def get_slots(self, org_id, date)
-   · def book(self, slot_id, request_id)
-   · def release(self, slot_id)
- 🏛 **SQLiteScheduleGateway**
-   · def get_dates(self, org_id, limit_days)
-   · def get_slots(self, org_id, date)
-   · def book(self, slot_id, request_id)
-   · def release(self, slot_id)
- ƒ def get_gateway() -> ScheduleGateway

### `core/updates.py` (20 стр.)
- 🏛 **Update**

### `core/uploads.py` (67 стр.)
импорты: `PIL`, `config`
- ƒ def _process_upload_image(content: bytes, mime_type: str) -> tuple[bytes, str, str] — Ресайз + компрессия. Возвращает (content, mime_type, ext).

### `core/waitlist.py` (1322 стр.)
импорты: `config`, `core`, `storage`
- ƒ def _fmt_slot(slot_date, slot_time) — '2026-11-08', '15:30' -> '08 ноя, 15:30'.
- ƒ def _get_slot(slot_id)
- ƒ def _bot_username()
- ƒ def _clear_released_at(slot_id) — Сбрасывает released_at, чтобы воркер больше не сканировал слот.
- ƒ async def notify_waitlist_for_slot(slot_id) — Создаёт pending-офферы для подходящих заявок листа.
- ƒ async def run_backfill_for_slot(slot_id) — Возвращает число отправленных предложений переноса.
- ƒ async def _book_slot_for_waitlist_client(user_id, slot, service_id_override) — Обёртка над create_booking_unified для листа ожидания.
- ƒ def _fulfill_waitlists_for_booking(user_id, org_id, service_id, slot_date, request_id) — Помечает fulfilled все активные заявки листа, подходящие под созданную запись.
- ƒ async def _notify_waitlist_entry_for_free_slots(waitlist_id) — При создании заявки: ищем уже свободные слоты, подходящие под неё,
- ƒ async def _send_single_offer(user_id, waitlist_id, offer) — Отправляет уведомление по одному офферу. Старый формат (1 кнопка ✅ + ❌).
- ƒ async def _send_grouped_offers(user_id, waitlist_id, offers) — Отправляет одно сообщение с несколькими слотами и выбором (кнопки по слотам).
- ƒ async def _flush_pending_offers() — Отправляет pending-офферы группами, но только когда самая старая группа
- ƒ async def _resend_remaining_offers_for_group(user_id, waitlist_id, exclude_offer_ids) — После неудачной попытки (слот занят) или после отмены — переотправляет
- ƒ async def handle_callback(uid, payload, message_id)
- ƒ async def _edit_or_send(uid, message_id, text, buttons)
- ƒ async def _scan_released_slots()
- ƒ async def _process_released_slot(slot_row)
- ƒ def _fulfill_waitlist_on_bookings_sync() — Sync-версия: выполняется в отдельном потоке (asyncio.to_thread).
- ƒ async def _sweep_stale_waitlists() — Проходит по активным заявкам, у которых нет pending/sent офферов,
- ƒ async def _fulfill_waitlist_on_bookings() — Помечает waitlist-заявки fulfilled, если у клиента появилась подходящая запись.
- ƒ async def _expire_daily()
- ƒ async def run_waitlist_worker()
- ƒ async def notify_single_waitlist_entry(waitlist_id) — Ручной пинок одной заявки из админки: ищем ближайший свободный слот,

### `core/channels/__init__.py` (0 стр.)
_пусто / без явных объявлений_

### `core/channels/base.py` (58 стр.)
- 🏛 **UserBlocked** — Клиент заблокировал бота в канале.
- 🏛 **ChannelError** — Прочие ошибки канала (сеть, API, retry exhausted).
- 🏛 **Channel**
-   · async def send_message(self, user_id, text: str, buttons: list | None, fmt: str | None) -> dict
-   · async def send_with_image(self, user_id, text: str, image_token: str, buttons: list | None, fmt: str | None) -> dict
-   · async def send_with_file(self, user_id, text: str, file_token: str, buttons: list | None, fmt: str | None) -> dict
-   · async def edit_message(self, user_id, message_id, text: str, buttons: list | None, fmt: str | None) -> dict | None
-   · async def delete_message(self, user_id, message_id) -> dict | None
-   · async def upload_file(self, content, filename: str, mime: str, upload_type: str) -> str
-   · async def set_commands(self, commands: list) -> None

### `core/channels/max.py` (119 стр.)
импорты: `core`
- 🏛 **MaxChannel**
-   · async def send_message(self, user_id, text, buttons, fmt)
-   · async def send_with_image(self, user_id, text, image_token, buttons, fmt)
-   · async def send_with_file(self, user_id, text, file_token, buttons, fmt)
-   · async def edit_message(self, user_id, message_id, text, buttons, fmt)
-   · async def delete_message(self, user_id, message_id)
-   · async def upload_file(self, content, filename, mime, upload_type)
-   · async def set_commands(self, commands)
- ƒ def _cache_max_upload(result, content, mime)

### `core/channels/registry.py` (99 стр.)
импорты: `core`, `storage`
- ƒ def get_channel(platform: str) -> Channel
- ƒ def _default_platform(org_id) -> str — Канал по умолчанию из настроек организации (фоллбэк — max).
- ƒ def _identity_platforms(user_id: str) — Паспорта клиента в порядке приоритета: [(platform, platform_uid), ...].
- ƒ def get_channels_for_client(user_id, org_id) — Все доступные каналы клиента — в порядке приоритета отправки.
- ƒ def get_channel_for_client(user_id, org_id) -> tuple[Channel, str, str] — Возвращает (channel, platform_user_id, platform) для основной отправки.

### `core/channels/vk.py` (281 стр.)
импорты: `core`, `httpx`, `storage`
- ƒ def _load_bot() — Активный VK-бот (token, group_id) с кэшем на минуту.
- ƒ def reset_bot_cache() — Сбросить кэш бота (после смены токена в админке).
- ƒ async def api_call(method, params, token, retries: int) — Вызов метода VK API. Возвращает поле response, бросает при ошибке.
- ƒ def _button(b) — Кнопка MAX-формата → кнопка клавиатуры VK.
- ƒ def _keyboard(buttons) — Список рядов кнопок MAX → inline-клавиатура VK.
- ƒ async def _send(peer_id, text, buttons, attachments) — Общая отправка: peer_id — id пользователя VK (диалог с сообществом).
- ƒ async def answer_event(raw) — Гасим «крутилку» на нажатой inline-кнопке (иначе клиент ждёт ответа).
- 🏛 **VkChannel**
-   · async def send_message(self, user_id, text, buttons, fmt)
-   · async def send_with_image(self, user_id, text, image_token, buttons, fmt)
-   · async def send_with_file(self, user_id, text, file_token, buttons, fmt)
-   · async def edit_message(self, user_id, message_id, text, buttons, fmt)
-   · async def delete_message(self, user_id, message_id)
-   · async def upload_file(self, content, filename, mime, upload_type, user_id) — Загрузка в VK. Фото — через photos, остальное — через docs.
-   · async def set_commands(self, commands) — VK не поддерживает список команд бота в интерфейсе — no-op.

### `core/channels/vk_text.py` (68 стр.)
импорты: `httpx`
- ƒ async def _shorten(url) — Сокращает URL через clck.ru; при ошибке возвращает как есть.
- ƒ async def vk_text(text) — VK не рендерит Markdown. Готовим текст:

### `core/webhook_adapters/max.py` (75 стр.)
импорты: `core`
- ƒ def _user_info(d: dict) -> dict
- ƒ def parse(raw: dict) -> Update | None

### `core/webhook_adapters/vk.py` (105 стр.)
импорты: `core`
- ƒ def _payload_str(payload) -> str — VK присылает payload строкой или объектом; нам нужен короткий код.
- ƒ def _parse_message_new(obj: dict)
- ƒ def _parse_message_event(obj: dict)
- ƒ def parse_event(data: dict) — dict из тела POST → Update | None (None = событие нам не нужно).

### `handlers/__init__.py` (0 стр.)
_пусто / без явных объявлений_

### `handlers/admin.py` (127 стр.)
импорты: `core`, `storage`
- ƒ async def try_handle(uid: int, text: str) -> bool
- ƒ def _gen_slots(org_id, branch_id, doctor_id)
- ƒ async def show_superadmin_panel(uid: int, message_id: str | None)

### `handlers/booking.py` (403 стр.)
импорты: `config`, `core`, `storage`
- ƒ def _row_get(row, key, default) — Безопасное чтение из sqlite3.Row — не падает, если ключа нет.
- ƒ def _resolve_org_name(uid, org_id) — Имя организации для приветствия. Fallback: client.org_id → первая org → 'наша клиника'.
- ƒ def main_menu_buttons(uid, platform) — Единая сборка главного меню для всех каналов.
- ƒ def back_to_menu_buttons(uid)
- ƒ def normalize_phone(text: str)
- ƒ def history_repeat_buttons(rows, max_buttons)
- ƒ def format_history(rows, show_all)
- ƒ async def welcome(uid, org_id, message_id, platform)
- ƒ async def handle_callback(uid, payload, message_id)
- ƒ async def handle_input(uid, text)
- ƒ async def _edit_or_send(uid, message_id, text, buttons, fmt)

### `handlers/client_confirm_callbacks.py` (154 стр.)
импорты: `core`, `storage`
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool
- ƒ async def _edit_or_send(uid, message_id, text, buttons)

### `handlers/merge_callbacks.py` (26 стр.)
импорты: `core`
- ƒ async def handle(uid, payload, message_id)

### `handlers/reminder_callbacks.py` (130 стр.)
импорты: `core`, `storage`
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool
- ƒ async def _edit_or_send(uid, message_id, text, buttons)

### `handlers/report_callbacks.py` (97 стр.)
импорты: `core`, `storage`
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool

### `handlers/request_callbacks.py` (112 стр.)
импорты: `config`, `core`, `storage`
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool
- ƒ async def _edit_or_send(uid, message_id, text)

### `handlers/review_callbacks.py` (158 стр.)
импорты: `core`, `storage`
- ƒ def _edit_or_send(uid, message_id, text, buttons)
- ƒ def _build_public_links(settings) — Возвращает список [(label, url), ...] для публичных площадок.
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool

### `handlers/start.py` (5 стр.)
импорты: `handlers`
- ƒ async def cmd_start(uid, platform)

### `handlers/superadmin_callbacks.py` (193 стр.)
импорты: `config`, `core`, `handlers`, `storage`
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool
- ƒ async def _show_pending(uid, message_id)
- ƒ async def _edit_or_send(uid, message_id, text, buttons)
- ƒ async def handle_text(uid: int, text: str) -> bool

### `handlers/unsub_callbacks.py` (99 стр.)
импорты: `core`, `storage`
- ƒ async def _edit_or_send(uid, message_id, text, buttons) — Пытаемся отредактировать сообщение; при неудаче — отправляем новое.
- ƒ async def handle(uid: int, payload: str, message_id: str | None) -> bool

### `handlers/visit_callbacks.py` (193 стр.)
импорты: `core`, `storage`
- ƒ def _resolve_org(uid, requested_org)
- ƒ def _fmt_time(scheduled_at)
- ƒ async def send_today(uid, requested_org)
- ƒ async def handle(uid, payload, message_id) — vis:today | vis:done:<id> | vis:no:<id>

### `mini/.env.example` (1 стр.)

### `mini/booking.db` (0 стр.)

### `mini/index.html` (13 стр.)

### `mini/package-lock.json` (1698 стр.)

### `mini/package.json` (19 стр.)

### `mini/vite.config.js` (16 стр.)
_пусто / без явных объявлений_

### `mini/src/App.jsx` (63 стр.)
- ƒ function getStartParam()

### `mini/src/ClientApp.jsx` (281 стр.)
- ƒ function loadPreselectedSlot()
- ƒ function handleRepeat(servicesList)
- ƒ function pickService(svc)
- ƒ function pickDate(d)
- ƒ function pickSlot(s)
- ƒ function toggleFavorite(doctorId)
- ƒ function submitBooking(payload)
- ƒ function reset()
- ƒ function openWaitlistForm()
- ƒ function openDoctorPicker()
- ƒ function closeWaitlistForm()

### `mini/src/api.js` (47 стр.)
- ƒ function getInitData()
- ƒ function request(path, options = {})

### `mini/src/main.jsx` (10 стр.)
_пусто / без явных объявлений_

### `mini/src/theme.css` (2506 стр.)

### `mini/src/admin/AdminApp.jsx` (274 стр.)
- ƒ function loadMe(currentOrg)
- ƒ function handleOrgChange(e)
- ƒ function openTab(id)
- ƒ function handleDashboardOpen(status, datePreset)

### `mini/src/admin/AnalyticsPage.jsx` (487 стр.)
- ƒ function pad(n)
- ƒ function isoDate(d)
- ƒ function addDays(d, n)
- ƒ function humanDate(iso)
- ƒ function presetRange(id)
- ƒ function fmtMoney(n)
- ƒ function fmtPct(n)
- ƒ function DeltaBadge({ value, suffix = '%', invert = false })
- ƒ function MetricCard({ label, value, delta, invert = false, hint })
- ƒ function BarChart({ items, valueKey = 'count', labelKey = 'name', valueSuffix = '', showRevenue = false, onItemClick = null })
- ƒ function choosePreset(id)
- ƒ function handleExport(format)

### `mini/src/admin/AuditLogPage.jsx` (193 стр.)
- ƒ function actionLabel(action)
- ƒ function humanTs(iso)
- ƒ function tryJson(str)
- ƒ function load(showSpinner = true)
- ƒ function changeFilter(id)
- ƒ const p = (n) =>

### `mini/src/admin/BlockedUsersPage.jsx` (102 стр.)
- ƒ function humanTs(iso)
- ƒ function load()
- ƒ function handleUnblock(userId)
- ƒ const p = (n) =>

### `mini/src/admin/BroadcastsPage.jsx` (1192 стр.)
- ƒ function formatScheduled(iso)
- ƒ function ManualBroadcasts({ orgId })
- ƒ function load()
- ƒ function openEdit(b)
- ƒ function handleDuplicate(bid)
- ƒ function handleCancel(bid)
- ƒ function handleUnschedule(bid)
- ƒ function handleDelete(bid)
- ƒ function ManualBroadcastForm({ orgId, initial, onSaved, onCancel })
- ƒ function upd(key, value)
- ƒ function toggleService(sid)
- ƒ function selectAllServices()
- ƒ function handlePreview()
- ƒ function handleFileChange(e)
- ƒ function handleRemoveImage()
- ƒ function buildPayload()
- ƒ function handleSaveDraft()
- ƒ function handleSendNow()
- ƒ function handleSchedule()
- ƒ function ManualBroadcastDetailsModal({ orgId, bid, onClose })
- ƒ function AutoBroadcasts({ orgId })
- ƒ function load()
- ƒ function handleToggle(id)
- ƒ function handleDelete(id)
- ƒ function handleSave(form)
- ƒ function AutoBroadcastForm({ orgId, initial, onSave, onCancel })
- ƒ function handleFileChange(e)
- ƒ function insertVariable(varname)
- ƒ function handleRemoveImage()
- ƒ function handleSubmit()
- ƒ const p = (n) =>

### `mini/src/admin/ChannelsPage.jsx` (536 стр.)
- ƒ function BotEditModal({ bot, orgId, onClose, onSave, busy })
- ƒ function handleChange(field, value)
- ƒ function checkToken()
- ƒ function handleSave()
- ƒ function loadBots()
- ƒ function handleSaveBot(formData)
- ƒ function handleToggleBotStatus(botId, currentEnabled)
- ƒ function handleDeleteBot(botId)
- ƒ function handleRegisterCallback(botId)

### `mini/src/admin/ClientCardModal.jsx` (753 стр.)
- ƒ function humanTs(iso)
- ƒ function load()
- ƒ function handlePhotoUpload(e)
- ƒ function handlePhotoDelete()
- ƒ function addTag()
- ƒ function removeTag(t)
- ƒ function handleSaveCard()
- ƒ function handleResetNoShow()
- ƒ function handleToggleMarketing()
- ƒ function handleToggleBlock()
- ƒ function handleCancelRequest(requestId)
- ƒ function handleExport(format)
- ƒ const p = (n) =>

### `mini/src/admin/ClientMessageModal.jsx` (207 стр.)
- ƒ function humanSize(bytes)
- ƒ function handleFileChange(e)
- ƒ function clearFile()
- ƒ function handleSend()

### `mini/src/admin/ClientPrivacyModal.jsx` (112 стр.)
- ƒ function handleDelete()

### `mini/src/admin/ClientsPage.jsx` (108 стр.)
- ƒ function humanTs(iso)
- ƒ function load(q)
- ƒ function handleSearch(e)
- ƒ const p = (n) =>

### `mini/src/admin/CreateRequestModal.jsx` (596 стр.)
- ƒ function isoDate(d)
- ƒ function addDays(d, n)
- ƒ function humanDate(iso)
- ƒ function isPastSlot(dateIso, timeStr)
- ƒ function notifyMessage(result)
- ƒ function buildDailyLimitConfirmText(data)
- ƒ function pickClient(client)
- ƒ function clearSelectedClient()
- ƒ function submit()
- ƒ const p = (n) =>
- ƒ const sortedDoctors = (() =>

### `mini/src/admin/DashboardPage.jsx` (212 стр.)
- ƒ function todayHuman()
- ƒ function load(showSpinner = true)
- ƒ function open(status, datePreset = 'today')

### `mini/src/admin/DirectoriesPage.jsx` (1008 стр.)
- ƒ function todayIso()
- ƒ function formatStopBadge(stopDate)
- ƒ function servicesBadge(servicesCount)
- ƒ function BranchesSection({ orgId })
- ƒ function load()
- ƒ function handleSave(form)
- ƒ function handleDelete(id)
- ƒ function handleSetPrimary(id)
- ƒ function DoctorsSection({ orgId })
- ƒ function load()
- ƒ function handleSave(form)
- ƒ function handleDelete(id)
- ƒ function handlePhotoUpload(doctorId, file)
- ƒ function handlePhotoDelete(doctorId)
- ƒ function DoctorAvatarInline({ doctor, initials, uploading, onUpload, onDelete })
- ƒ function DoctorForm({ title, onClose, onSave, branches, initial })
- ƒ function handleSubmit()
- ƒ function CategoriesSection({ orgId })
- ƒ function load()
- ƒ function handleSave(form)
- ƒ function handleDelete(id)
- ƒ function ServicesSection({ orgId })
- ƒ function load()
- ƒ function handleSave(form)
- ƒ function handleDelete(id)
- ƒ function ModalForm({ title, onClose, onSave, fields, initial })
- ƒ function setField(key, value)
- ƒ function setSelectField(key, rawValue, nullable)
- ƒ function handleSubmit()
- ƒ const p = (n) =>

### `mini/src/admin/DoctorScheduleModal.jsx` (491 стр.)
- ƒ function todayIso()
- ƒ function newShiftForDay(weekday, defaultBranchId)
- ƒ function load()
- ƒ function addShift(wd)
- ƒ function removeShift(wd, key)
- ƒ function updateShift(wd, key, field, value)
- ƒ function toggleBreak(wd, key)
- ƒ function handleSaveAndApply()
- ƒ function handleAddException()
- ƒ function handleDeleteException(excId)
- ƒ function branchName(bid)
- ƒ const p = (n) =>

### `mini/src/admin/DoctorServicesModal.jsx` (256 стр.)
- ƒ function load()
- ƒ function toggleService(sid)
- ƒ function toggleAll(sidList)
- ƒ function selectAll()
- ƒ function selectSpecific()
- ƒ function handleSave()

### `mini/src/admin/DoctorStatsModal.jsx` (180 стр.)
- ƒ function fmtMoney(n)
- ƒ function fmtPct(n)
- ƒ function MetricCard({ label, value, hint })

### `mini/src/admin/EditRequestModal.jsx` (199 стр.)
- ƒ function formatTime(h, m)
- ƒ function loadSlotOptions()
- ƒ function handleServiceChange(newServiceId)
- ƒ function submit()

### `mini/src/admin/MarkVisitModal.jsx` (137 стр.)
- ƒ function handleConfirm(withPayment)

### `mini/src/admin/MoveRequestModal.jsx` (210 стр.)
- ƒ function isoDate(d)
- ƒ function addDays(d, n)
- ƒ function humanDate(iso)
- ƒ function handleMove()
- ƒ const p = (n) =>

### `mini/src/admin/RequestsPage.jsx` (478 стр.)
- ƒ function isoDate(d)
- ƒ function addDays(d, n)
- ƒ function todayIso()
- ƒ function plusDaysIso(n)
- ƒ function load()
- ƒ function priceByServiceId(serviceId)
- ƒ function changeStatus(newStatus)
- ƒ function changeDatePreset(id)
- ƒ function handleConfirm(id)
- ƒ function handleReject(id, wasConfirmed)
- ƒ function handleMarkNoShow(id)
- ƒ function handleMarkDone(payload)
- ƒ const p = (n) =>
- ƒ const activeDateLabel = (DATE_PRESETS.find((p) =>

### `mini/src/admin/ReviewsPage.jsx` (173 стр.)
- ƒ function humanTs(iso)
- ƒ function stars(rating)
- ƒ function load()
- ƒ const p = (n) =>

### `mini/src/admin/SchedulePage.jsx` (898 стр.)
- ƒ function pad(n)
- ƒ function isoDate(d)
- ƒ function startOfWeek(d)
- ƒ function addDays(d, n)
- ƒ function humanDay(d)
- ƒ function buildTimeRows(stepMin)
- ƒ function isPastDate(isoStr, timeStr)
- ƒ function loadSlots()
- ƒ function loadBranches()
- ƒ function loadServices()
- ƒ function loadAllOrgDoctors()
- ƒ function rememberChoice(serviceId, doctorId)
- ƒ function prevWeek()
- ƒ function nextWeek()
- ƒ function handleQuickCreateSave(date, time, serviceId, doctorId)
- ƒ function handleDeleteSlot(slotId)
- ƒ function handleCancelRequest(slot)
- ƒ function handleAddSlot()
- ƒ function handleGenerate()
- ƒ function handleRegenerateAll()
- ƒ function toggleDayOfWeek(d)
- ƒ function handleCellClick(iso, time)
- ƒ function QuickCreateSheet({ date, time, services, doctors, busy, onSave, onClose })
- ƒ function CellSheet({ date, time, slots, past, busy, onDeleteSlot, onCancelRequest, onAddAnother, onClose })

### `mini/src/admin/SettingsPage.jsx` (900 стр.)
- ƒ function update(field, value)
- ƒ function updateNumeric(field, raw)
- ƒ function updateWorkHours(dayKey, field, value)
- ƒ function toggleDay(dayKey, enabled)
- ƒ function handleSave()

### `mini/src/admin/VisitDetailsModal.jsx` (78 стр.)
- ƒ function humanTs(iso)
- ƒ const p = (n) =>

### `mini/src/admin/WaitlistPage.jsx` (571 стр.)
- ƒ function humanDate(iso)
- ƒ function humanTs(iso)
- ƒ function load()
- ƒ function loadServices()
- ƒ function handleNotify(wid)
- ƒ function handleFulfill(wid)
- ƒ function handleCancel(wid)
- ƒ function WaitlistEditModal({ orgId, services, initial, onClose, onSaved })
- ƒ function pickClient(c)
- ƒ function clearClient()
- ƒ function submit()
- ƒ const p = (n) =>

### `mini/src/admin/adminApi.js` (442 стр.)
- ƒ function getInitData()
- ƒ function buildUrl(path, orgId)
- ƒ function request(path, orgId, options = {})

### `mini/src/components/CalendarGrid.jsx` (86 стр.)
- ƒ function pad(n)
- ƒ function isoFor(day)
- ƒ function prevMonth()
- ƒ function nextMonth()

### `mini/src/components/DoctorPicker.jsx` (79 стр.)
_пусто / без явных объявлений_

### `mini/src/components/PhoneForm.jsx` (241 стр.)
- ƒ function humanDate(iso)
- ƒ function normalizePhone(text)
- ƒ function submit()

### `mini/src/components/ServiceList.jsx` (115 стр.)
- ƒ function toggleCollapse(groupKey)

### `mini/src/components/Success.jsx` (20 стр.)
_пусто / без явных объявлений_

### `mini/src/components/TimeGrid.jsx` (189 стр.)
- ƒ function humanDate(iso)
- ƒ function colorForBranch(branchId)
- ƒ function groupByTime(list)
- ƒ function sortedSlotsForFav(list)
- ƒ function renderDoctorChip(s)
- ƒ function renderTimeGroups(list)

### `mini/src/components/WaitlistForm.jsx` (146 стр.)
- ƒ function pad(n)
- ƒ function isoDate(d)
- ƒ function addDays(d, n)
- ƒ function submit()

### `mini/src/components/WaitlistPage.jsx` (201 стр.)
- ƒ function humanDate(iso)
- ƒ function load()
- ƒ function startCreateByService()
- ƒ function startCreateByDoctor()
- ƒ function pickService(svc)
- ƒ function pickDoctor(doc)
- ƒ function cancelEntry(wid)
- ƒ function closeApp()

### `routers/__init__.py` (0 стр.)
_пусто / без явных объявлений_

### `routers/admin_bots.py` (592 стр.)
импорты: `config`, `core`, `fastapi`, `httpx`, `pydantic`, `storage`
- ƒ async def list_org_bots(ctx: AdminCtx) — Список всех ботов организации.
- ƒ async def get_org_bot(bot_id: int, ctx: AdminCtx) — Получить детали бота.
- ƒ async def init_vk_bot(group_id: int, ctx: AdminCtx) — Инициализировать новый VK-бота.
- ƒ async def set_bot_token(bot_id: int, token: str, ctx: AdminCtx) — Обновить токен бота и включить его.
- ƒ async def update_bot(bot_id: int, enabled: Optional[bool], title: Optional[str], token: Optional[str], group_id: Optional[str], confirmation_code: Optional[str], ctx: AdminCtx) — Обновить настройки бота (включить/выключить, изменить название, токен, confirmation_code).
- ƒ async def remove_bot(bot_id: int, ctx: AdminCtx) — Удалить бота.
- ƒ async def ui_list_bots(ctx: AdminCtx) — Получить список ботов для админки (UI).
- 🏛 **CheckTokenBody**
- 🏛 **CheckTokenBody**
- ƒ async def vk_api(token, group_id, method, params) — Вызов VK API от имени конкретного бота (токен из bots).
- ƒ async def ui_check_bot_token(body: CheckTokenBody, ctx: AdminCtx) — Проверить токен бота через API платформы.
- 🏛 **AddBotBody**
- ƒ async def ui_add_bot(body: AddBotBody, ctx: AdminCtx) — Добавить новый бот (для админки).
- 🏛 **UpdateBotBody**
- ƒ async def ui_update_bot(bot_id: int, body: UpdateBotBody, ctx: AdminCtx) — Обновить бот (для админки).
- ƒ async def ui_register_callback(bot_id: int, ctx: AdminCtx) — Зарегистрировать Callback-адрес бота в VK (setCallbackServer + события).
- ƒ async def ui_delete_bot(bot_id: int, ctx: AdminCtx) — Удалить бот (для админки).

### `routers/admin_broadcasts.py` (466 стр.)
импорты: `core`, `fastapi`, `storage`
- ƒ def _check_image_id(ctx: AdminCtx, image_id)
- ƒ async def admin_broadcasts(ctx: AdminCtx)
- ƒ async def admin_broadcast_preview(request: Request, ctx: AdminCtx)
- ƒ async def admin_broadcast_create(request: Request, ctx: AdminCtx)
- ƒ async def admin_broadcast_update(request: Request, bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_start(bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_schedule(request: Request, bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_unschedule(bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_cancel(bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_duplicate(bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_delete(bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_details(bid: int, ctx: AdminCtx)
- ƒ async def admin_broadcast_sends(bid: int, ctx: AdminCtx)
- ƒ async def admin_auto_broadcasts(ctx: AdminCtx)
- ƒ async def admin_auto_broadcast_create(request: Request, ctx: AdminCtx)
- ƒ async def admin_auto_broadcast_update(request: Request, aid: int, ctx: AdminCtx)
- ƒ async def admin_auto_broadcast_delete(aid: int, ctx: AdminCtx)
- ƒ async def admin_auto_broadcast_toggle(aid: int, ctx: AdminCtx)
- ƒ async def admin_auto_broadcast_test(aid: int, ctx: AdminCtx) — Отправляет админу тестовое сообщение с подставленными фиктивными данными.

### `routers/admin_core.py` (242 стр.)
импорты: `config`, `core`, `fastapi`, `storage`
- ƒ async def admin_me(ctx: AdminCtx)
- ƒ async def admin_update_org(request: Request, ctx: AdminCtx)
- ƒ async def admin_orgs(ctx: AdminCtx)
- ƒ async def admin_timezones(ctx: AdminCtx)
- ƒ async def admin_dashboard_today(ctx: AdminCtx)
- ƒ async def admin_analytics_summary(date_from: str, date_to: str, branch_id: int | None, doctor_id: int | None, ctx: AdminCtx)
- ƒ async def admin_analytics_doctor(doctor_id: int, date_from: str, date_to: str, ctx: AdminCtx) — Сводка по одному специалисту за период. Для модалки в аналитике.
- ƒ async def admin_analytics_export(date_from: str, date_to: str, format: str, branch_id: int | None, doctor_id: int | None, ctx: AdminCtx) — Экспорт аналитики в CSV/XLSX/PDF. Отправляет файл в чат админу.
- ƒ async def admin_audit_log(limit: int, offset: int, action: str | None, date_from: str | None, date_to: str | None, ctx: AdminCtx)

### `routers/admin_directories.py` (1172 стр.)
импорты: `config`, `core`, `fastapi`, `storage`
- ƒ async def admin_slots(date_from: str, date_to: str, branch_id: int | None, doctor_id: int | None, ctx: AdminCtx)
- ƒ async def admin_slots_available(date_from: str, date_to: str, service_id: str | None, branch_id: int | None, doctor_id: int | None, slots_count: int | None, ctx: AdminCtx) — Свободные слоты для форм «Создать запись» и «Перенести запись».
- ƒ async def admin_create_slot(request: Request, ctx: AdminCtx)
- ƒ async def admin_delete_slot(slot_id: int, ctx: AdminCtx)
- ƒ async def admin_generate_slots(request: Request, ctx: AdminCtx)
- ƒ def _valid_hhmm(t)
- ƒ def _times_overlap(a_start, a_end, b_start, b_end) — Пересекаются ли интервалы 'HH:MM' (без учёта перерыва, только основное время).
- ƒ async def admin_get_doctor_schedule(doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_set_doctor_schedule(request: Request, doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_get_doctor_services(doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_set_doctor_services(request: Request, doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_list_schedule_exceptions(doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_create_schedule_exception(request: Request, doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_delete_schedule_exception(doctor_id: int, exc_id: int, ctx: AdminCtx)
- ƒ async def admin_regenerate_doctor_slots(doctor_id: int, request: Request, ctx: AdminCtx)
- ƒ async def admin_regenerate_all_slots(request: Request, ctx: AdminCtx)
- ƒ async def admin_branches(ctx: AdminCtx)
- ƒ async def admin_create_branch(request: Request, ctx: AdminCtx)
- ƒ async def admin_update_branch(request: Request, branch_id: int, ctx: AdminCtx)
- ƒ async def admin_delete_branch(branch_id: int, ctx: AdminCtx)
- ƒ async def admin_set_primary_branch(branch_id: int, ctx: AdminCtx)
- ƒ def _doctor_photo_url(photo_upload_id)
- ƒ async def admin_doctors(branch_id: int | None, ctx: AdminCtx)
- ƒ def _attach_review_stats(doctors: list, org_id: int) — Батч-добавление avg_rating и reviews_count в каждый dict.
- ƒ async def admin_create_doctor(request: Request, ctx: AdminCtx)
- ƒ async def admin_update_doctor(request: Request, doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_delete_doctor(doctor_id: int, ctx: AdminCtx)
- ƒ async def admin_doctor_upload_photo(doctor_id: int, file: UploadFile, ctx: AdminCtx) — Загружает фото специалиста. Сжимает, хранит локально.
- ƒ async def admin_doctor_delete_photo(doctor_id: int, ctx: AdminCtx) — Отвязывает фото специалиста.
- ƒ async def admin_doctor_reviews(doctor_id: int, ctx: AdminCtx) — Все отзывы по специалисту + агрегат. Для модалки «Эффективность».
- ƒ async def admin_set_doctor_schedule_stop(doctor_id: int, request: Request, ctx: AdminCtx) — Устанавливает дату, до которой генерируются слоты из графика.
- ƒ async def admin_services(ctx: AdminCtx)
- ƒ async def admin_create_service(request: Request, ctx: AdminCtx)
- ƒ async def admin_update_service(request: Request, service_id: str, ctx: AdminCtx)
- ƒ async def admin_delete_service(service_id: str, ctx: AdminCtx)
- ƒ async def admin_service_categories(ctx: AdminCtx)
- ƒ async def admin_create_service_category(request: Request, ctx: AdminCtx)
- ƒ async def admin_update_service_category(request: Request, cat_id: int, ctx: AdminCtx)
- ƒ async def admin_delete_service_category(cat_id: int, ctx: AdminCtx)

### `routers/admin_requests.py` (1660 стр.)
импорты: `config`, `core`, `fastapi`, `handlers`, `storage`
- ƒ async def admin_requests(date_from: str | None, date_to: str | None, status: str | None, auto_done: str | None, page: int, per_page: int, ctx: AdminCtx)
- ƒ async def admin_clients_search(q: str, limit: int, ctx: AdminCtx)
- ƒ async def admin_client_marketing(request: Request, user_id: str, ctx: AdminCtx)
- ƒ async def admin_client_export_json(user_id: str, ctx: AdminCtx) — Выгрузка всех данных клиента (152-ФЗ, право на доступ) в JSON.
- ƒ async def admin_client_delete(user_id: str, ctx: AdminCtx) — Удаление данных клиента (152-ФЗ, право на забвение).
- ƒ async def admin_block_client(request: Request, user_id: str, ctx: AdminCtx)
- ƒ async def admin_unblock_client(user_id: str, ctx: AdminCtx)
- ƒ async def admin_blocked_users(ctx: AdminCtx)
- ƒ async def admin_client_card(user_id: str, ctx: AdminCtx) — Полная карточка клиента: профиль, история, услуги, специалисты, предстоящие.
- ƒ async def admin_client_card_update(request: Request, user_id: str, ctx: AdminCtx) — Обновляет заметки и теги клиента.
- ƒ async def admin_client_reset_no_show(user_id: str, ctx: AdminCtx) — Сбрасывает счётчик неявок клиента.
- ƒ async def admin_client_upload_photo(user_id: str, file: UploadFile, ctx: AdminCtx) — Загружает фото клиента. Сжимает, хранит локально, отдаёт через public_token.
- ƒ async def admin_client_delete_photo(user_id: str, ctx: AdminCtx) — Отвязывает фото клиента. Файл на диске остаётся, но ссылка перестаёт быть активной.
- ƒ async def admin_client_send_message_with_file(user_id: str, file: UploadFile, text: str, ctx: AdminCtx) — Отправляет клиенту сообщение с файлом. Фото сжимаются.
- ƒ async def admin_client_send_message(request: Request, user_id: str, ctx: AdminCtx) — Отправить произвольное сообщение клиенту (пока только через MAX).
- ƒ async def admin_client_export_file(user_id: str, format: str, target: str, ctx: AdminCtx) — Генерирует CSV/XLSX/PDF и отправляет файл:
- ƒ async def admin_request_slot_options(request_id: int, ctx: AdminCtx) — Сколько подряд идущих слотов доступно для этой записи.
- ƒ async def admin_request_edit(request: Request, request_id: int, ctx: AdminCtx) — Редактирование услуги и/или количества слотов существующей записи.
- ƒ async def admin_request_move(request: Request, request_id: int, ctx: AdminCtx) — Перенос записи на новый слот. Освобождает старые, занимает новые.
- ƒ async def admin_request_create(request: Request, ctx: AdminCtx)
- ƒ async def admin_mark_done(request: Request, request_id: int, ctx: AdminCtx)
- ƒ async def admin_mark_no_show(request_id: int, ctx: AdminCtx)
- ƒ async def _mark_visit(ctx: AdminCtx, request_id: int, new_status: str, body: dict | None)
- ƒ async def admin_update_payment(request: Request, request_id: int, ctx: AdminCtx)
- ƒ async def admin_confirm(request_id: int, ctx: AdminCtx)
- ƒ async def admin_reject(request_id: int, ctx: AdminCtx)
- ƒ async def admin_waitlist_list(status: str | None, service_id: str | None, doctor_id: int | None, branch_id: int | None, limit: int, offset: int, ctx: AdminCtx)
- ƒ async def admin_waitlist_create(request: Request, ctx: AdminCtx)
- ƒ async def admin_waitlist_update(wid: int, request: Request, ctx: AdminCtx)
- ƒ async def admin_waitlist_cancel(wid: int, ctx: AdminCtx)
- ƒ async def admin_waitlist_notify(wid: int, ctx: AdminCtx)
- ƒ async def admin_waitlist_fulfill(wid: int, request: Request, ctx: AdminCtx)

### `routers/admin_reviews.py` (89 стр.)
импорты: `core`, `fastapi`, `storage`
- ƒ async def admin_reviews_list(filter: str | None, doctor_id: int | None, rating: int | None, limit: int, offset: int, ctx: AdminCtx)
- ƒ async def admin_client_reviews(user_id: str, ctx: AdminCtx)

### `routers/admin_settings.py` (160 стр.)
импорты: `core`, `fastapi`, `storage`
- ƒ def _validate_settings(new_settings: dict) -> tuple[bool, str]
- ƒ async def admin_get_settings(ctx: AdminCtx)
- ƒ async def admin_set_settings(request: Request, ctx: AdminCtx)

### `routers/admin_uploads.py` (169 стр.)
импорты: `config`, `core`, `fastapi`, `httpx`, `storage`
- ƒ async def admin_upload(file: UploadFile, ctx: AdminCtx)
- ƒ async def admin_upload_file(upload_id: int, request: Request, ctx: AdminCtx)
- ƒ async def public_upload_file(public_token: str) — Публичная отдача картинки для <img src="...">.

### `routers/mini_app.py` (595 стр.)
импорты: `core`, `fastapi`, `handlers`, `storage`
- ƒ async def mini_me(user: dict)
- ƒ async def mini_set_favorite_doctor(request: Request, user: dict)
- ƒ async def mini_services(user: dict)
- ƒ async def mini_dates(service_id: str, user: dict)
- ƒ async def mini_slots(service_id: str, date: str, user: dict)
- ƒ async def mini_doctors(user: dict) — Список специалистов организации для клиентского Mini App.
- ƒ async def mini_history(request_id: int, user: dict) — Данные прошлой заявки — для кнопки «Повторить» в Mini App.
- ƒ async def mini_book(request: Request, user: dict)
- ƒ async def mini_slot_details(slot_id: int, user: dict)
- ƒ async def mini_waitlist_create(request: Request, user: dict)
- ƒ async def mini_waitlist_list(user: dict)
- ƒ async def mini_waitlist_cancel(wid: int, user: dict)

### `routers/webhook.py` (100 стр.)
импорты: `config`, `core`, `fastapi`, `httpx`
- ƒ async def ensure_webhook_subscribed()
- ƒ async def register_bot_commands()
- ƒ async def startup() — Вызывается из lifespan приложения после init_db().
- ƒ async def webhook(request: Request)

### `routers/webhook_vk.py` (170 стр.)
импорты: `core`, `fastapi`, `storage`
- ƒ def _internal_user_id(vk_uid: str, org_id) -> str — Внутренний user_id клиента по VK-id. Заводит «паспорт» при первом контакте.
- ƒ async def _autofill_vk_profile(vk_uid: str, bot) -> None — Заполняет пустые поля профиля VK-клиента данными users.get.
- ƒ async def vk_webhook(slug: str, request: Request)
- ƒ async def vk_webhook_ping(slug: str) — Проверка адреса из браузера: бот есть — 'ok'.

### `storage/__init__.py` (0 стр.)
_пусто / без явных объявлений_

### `storage/db.py` (5704 стр.)
импорты: `config`
- ƒ def db() — Соединение с БД: ждёт блокировку до 30 с, WAL, row_factory.
- ƒ def db_ctx() — Контекстный менеджер для соединения с БД.
- ƒ def _tz_obj(tz_name: str) -> ZoneInfo
- ƒ def get_org_timezone(org_id: int) -> str
- ƒ def set_org_timezone(org_id: int, tz_name: str)
- ƒ def now_for_org(org_id: int) -> datetime — Наивный datetime в локальной таймзоне организации.
- ƒ def today_for_org(org_id: int) -> str
- ƒ def _ensure_column(conn, table, column, ddl)
- ƒ def init_db()
- ƒ def log_audit(org_id, user_id, action, entity_type, entity_id, payload)
- ƒ def list_audit_log(org_id, limit, offset, action, date_from, date_to)
- ƒ def get_orgs_with_evening_summary() — Возвращает организации в формате (org_id, hour_local).
- ƒ def get_dashboard_today(org_id, today_str) — Сводка по сегодняшнему дню. today_str в локальной таймзоне организации.
- ƒ def get_today_requests_for_summary(org_id, today_str)
- ƒ def save_uploaded_image_full(token, file_path, mime_type, original_filename, file_size, org_id, uploaded_by) — Сохраняет запись о загруженном файле. Возвращает (id, public_token).
- ƒ def get_uploaded_image_by_id(upload_id)
- ƒ def list_temp_exports_older_than(minutes) — Возвращает id, file_path записей uploaded_images с mime csv/xlsx/pdf,
- ƒ def list_orphan_uploaded_files(org_id, extensions) — Возвращает список file_path на диске в uploads/{org_id}/ с расширением из extensions,
- ƒ def delete_uploaded_image_file(upload_id) — Удаляет файл с диска и запись из uploaded_images.
- ƒ def get_uploaded_image_by_public_token(public_token)
- ƒ def update_uploaded_image_token(upload_id, token)
- ƒ def get_uploaded_image(token: str) — Legacy-поиск по token. Возвращает Row или None.
- ƒ def create_org(name: str) -> int
- ƒ def list_orgs()
- ƒ def get_org(oid: int)
- ƒ def get_org_settings(org_id: int) -> dict
- ƒ def set_org_settings(org_id: int, settings: dict) — Сохраняет настройки. timezone вынимается и пишется в отдельную колонку.
- ƒ def update_org_name(org_id: int, name: str) -> bool — Переименование организации. Возвращает True при успехе.
- ƒ def is_superadmin_db(platform, platform_uid) — Проверка суперадмина по платформе и ID. Новая схема — против БД.
- ƒ def is_superadmin(uid) — Обратная совместимость: проверка MAX-суперадмина через конфиг (deprecated).
- ƒ def is_admin(uid)
- ƒ def upsert_superadmin(platform, platform_uid, name) — Добавить или обновить суперадмина. Идемпотентна.
- ƒ def list_superadmins() — Все суперадмины.
- ƒ def delete_superadmin(platform, platform_uid) — Удалить суперадмина.
- ƒ def get_admin_org(uid)
- ƒ def add_admin(uid, first_name, org_id, added_by)
- ƒ def remove_admin(uid)
- ƒ def list_admins()
- ƒ def admins_of_org(org_id)
- ƒ def add_pending(uid, first_name, username)
- ƒ def list_pending()
- ƒ def remove_pending(uid)
- ƒ def get_services(org_id)
- ƒ def get_service(sid)
- ƒ def list_services_admin(org_id)
- ƒ def create_service(org_id, sid, name, price, prep, duration_min, category_id, buffer_min, revisit_interval_days)
- ƒ def update_service(sid, name, price, prep, duration_min, active, category_id, buffer_min, revisit_interval_days)
- ƒ def delete_service(sid)
- ƒ def list_service_categories(org_id) — Список категорий организации с количеством услуг в каждой.
- ƒ def get_service_category(cat_id)
- ƒ def create_service_category(org_id, name, sort_order)
- ƒ def update_service_category(cat_id, name, sort_order)
- ƒ def delete_service_category(cat_id) — Удаляет категорию, только если в ней нет услуг.
- ƒ def set_state(user_id, state, context)
- ƒ def get_state(user_id)
- ƒ def clear_state(user_id)
- ƒ def search_clients(org_id: int, query: str, limit: int)
- ƒ def get_client_platforms(user_id) — Платформы клиента по client_identities: список ['max', 'vk'].
- ƒ def get_client_platforms_batch(user_ids) — Каналы пачки клиентов: {user_id: ['max', 'vk']}.
- ƒ def merge_client_into(stub_uid, real_uid) — Переносит записи телефонного стаба (phone:...) на реального клиента.
- ƒ def get_or_create_client_by_phone(org_id, first_name, last_name, middle_name, phone)
- ƒ def upsert_client(user_id, org_id, first_name, last_name, middle_name, phone, gender, birth_date)
- ƒ def _ensure_identity_for_user(conn, user_id: str) -> None — Создаёт MAX-паспорт для «настоящего» user_id (не phone:...).
- ƒ def get_client_identities(user_id) — Все «паспорта» клиента: список строк (platform, platform_uid, ...).
- ƒ def get_identity_by_platform_uid(platform, platform_uid) — Паспорт по id в канале: вернёт строку или None.
- ƒ def link_client_identity(user_id, platform, platform_uid, is_primary: int) — Привязывает паспорт (platform, platform_uid) к клиенту user_id.
- ƒ def touch_client_identity(user_id, platform) — Отмечает активность клиента в канале (для приоритета «последний активный»).
- ƒ def unlink_client_identity(user_id, platform) — Удаляет паспорт — при отвязке канала или удалении данных по 152-ФЗ.
- ƒ def list_bots(org_id, platform, only_enabled: bool) — Список ботов, опционально по организации / платформе.
- ƒ def get_bot(bot_id)
- ƒ def get_bot_by_slug(slug) — Бот по slug — для маршрутизации /webhook/{bot_slug} (E4).
- ƒ def get_bot_for_org(org_id, platform, only_enabled: bool) — Основной бот организации на платформе (сейчас MAX-бот из конфига).
- ƒ def upsert_bot(org_id, platform, slug, token, webhook_secret, title, enabled: int, group_id, confirmation_code) — Создаёт или обновляет бота. Ключ — slug (он уникален глобально).
- ƒ def set_bot_enabled(bot_id, enabled: bool)
- ƒ def delete_bot(bot_id) — Удалить бота.
- ƒ def get_client(user_id)
- ƒ def set_marketing_opt_out(user_id, opt_out: bool)
- ƒ def get_marketing_opt_out(user_id)
- ƒ def get_marketing_opt_out_batch(user_ids)
- ƒ def set_favorite_doctor(user_id, doctor_id) — Ставит/снимает любимого врача. doctor_id=None или 0 — снять.
- ƒ def get_favorite_doctor(user_id)
- ƒ def set_consent_152fz(user_id, consent) — Фиксирует согласие на обработку ПД (152-ФЗ). timestamp — серверное.
- ƒ def export_client_data(user_id, org_id) — Выгрузка всех данных клиента в JSON-совместимом виде (152-ФЗ).
- ƒ def delete_client_data(user_id, org_id) — Удаление PII клиента по 152-ФЗ.
- ƒ def recalculate_last_visit(user_id, org_id)
- ƒ def recalculate_all_last_visits(org_id)
- ƒ def autocomplete_past_visits(grace_hours, org_id) — Прошедшие confirmed → done с автозаполнением суммы по прайсу.
- ƒ def cancel_stale_pending(timeout_min, org_id) — Отменяет pending-заявки старше timeout_min и освобождает ВСЕ слоты записи.
- ƒ def list_visits_for_date(org_id, date_str)
- ƒ def touch_client_visit(user_id, when_iso)
- ƒ def add_history(org_id, user_id, service_name, scheduled_at, phone, address, doctor, branch_id, doctor_id, slot_id, status, service_id)
- ƒ def get_history(user_id)
- ƒ def get_history_upcoming(user_id)
- ƒ def get_history_all(user_id)
- ƒ def get_request(request_id)
- ƒ def slots_needed_for_service(service_id, step_min) — Сколько подряд идущих слотов займёт услуга (с учётом буфера).
- ƒ def find_consecutive_slots(slot_id, slots_needed, step_min) — Проверяет, что от slot_id подряд идут slots_needed слотов
- ƒ def filter_slots_by_duration(org_id, date, base_slots, slots_needed, step_min) — Фильтрует свободные слоты: оставляет только те, для которых есть
- ƒ def update_request_status(request_id, status, admin_id)
- ƒ def set_request_payment(request_id, actual_amount, payment_method)
- ƒ def get_stats(org_id)
- ƒ def create_branch(org_id, name, address, phone)
- ƒ def list_branches(org_id)
- ƒ def get_primary_branch(org_id) — Основной филиал org. Если ни одного не помечено — первый по id.
- ƒ def set_primary_branch(branch_id) — Помечает филиал основным, снимает флаг с других в его org.
- ƒ def get_branch(bid)
- ƒ def update_branch(bid, name, address, phone)
- ƒ def delete_branch(bid) — Удаление филиала с проверками и чисткой.
- ƒ def create_doctor(branch_id, name, specialty, education, courses, about)
- ƒ def list_doctors(branch_id) — Врачи, работающие в филиале: либо основной филиал = branch_id,
- ƒ def list_doctors_by_org(org_id)
- ƒ def get_doctor_branches(doctor_id) — Список филиалов, где врач работает: основной (doctors.branch_id) +
- ƒ def get_doctor_services(doctor_id) — Список service_id, привязанных к врачу.
- ƒ def set_doctor_services(doctor_id, service_ids) — Полная перезапись привязки. Пустой список = делает все услуги.
- ƒ def doctor_makes_service(doctor_id, service_id) — True, если врач оказывает услугу.
- ƒ def doctor_makes_service_batch(doctor_ids, service_id) — Батч-проверка: {doctor_id: True/False}. Пустой список привязок = делает все.
- ƒ def list_doctors_for_service(org_id, service_id) — Все врачи org с флагом делает/не делает услугу.
- ƒ def get_doctor(did)
- ƒ def set_doctor_photo(did, upload_id) — Привязывает/отвязывает фото специалиста. upload_id=None — убрать.
- ƒ def set_doctor_schedule_stop_date(did, stop_date) — stop_date: 'YYYY-MM-DD' или None.
- ƒ def update_doctor(did, name, specialty, branch_id, education, courses, about)
- ƒ def delete_doctor(did) — Удаление врача с проверками и чисткой.
- ƒ def get_doctor_shifts(doctor_id) — Смены врача: список Row с полями
- ƒ def set_doctor_shifts(doctor_id, shifts) — Полная перезапись смен. shifts = список dict:
- ƒ def get_doctor_schedule(doctor_id)
- ƒ def list_schedule_exceptions(doctor_id)
- ƒ def get_schedule_exception(doctor_id, exc_id)
- ƒ def create_schedule_exception(doctor_id, date_from, date_to, reason)
- ƒ def delete_schedule_exception(doctor_id, exc_id)
- ƒ def regenerate_doctor_slots(doctor_id, horizon_days) — Синхронизирует auto-слоты врача с его сменами на горизонте.
- ƒ def regenerate_all_slots_for_org(org_id, horizon_days) — Пересоздаёт авто-слоты для всех врачей организации.
- ƒ def add_slot(org_id, branch_id, doctor_id, date, time, service_id)
- ƒ def list_dates_with_slots(org_id, limit_days)
- ƒ def list_free_slots(org_id, date, service_id)
- ƒ def get_slot(slot_id)
- ƒ def book_slot(slot_id, request_id)
- ƒ def release_slot(slot_id, request_id) — Освобождает слот(ы) записи.
- ƒ def create_booking(org_id, user_id, service_name, scheduled_at, phone, address, doctor, branch_id, doctor_id, slot_ids, status, service_id) — slot_ids — список id слотов (первый = основной). Всё занимается атомарно.
- ƒ def count_active_future_requests(user_id, org_id)
- ƒ def count_slots_today(org_id)
- ƒ def has_active_request_for_slot(user_id, slot_id, phone)
- ƒ def has_active_request_at_time(user_id, org_id, scheduled_at, phone) — У клиента уже есть активная запись на это же время.
- ƒ def count_active_bookings_on_date(user_id, org_id, date_str) — Сколько активных записей на конкретную дату (YYYY-MM-DD).
- ƒ def list_active_bookings_on_date(user_id, org_id, date_str) — Список активных записей клиента на дату: id, service_name, scheduled_at, doctor.
- ƒ def block_user(user_id, org_id, phone, reason, blocked_by)
- ƒ def unblock_user(user_id)
- ƒ def is_user_blocked(user_id)
- ƒ def is_user_blocked_batch(user_ids)
- ƒ def list_blocked_users(org_id)
- ƒ def list_slots_range(org_id, date_from, date_to, branch_id, doctor_id)
- ƒ def create_slot(org_id, branch_id, doctor_id, date, time, service_id)
- ƒ def delete_slot(slot_id)
- ƒ def generate_slots_range(org_id, branch_id, doctor_id, date_from, days, days_of_week, time_start, time_end, step_min, service_id)
- ƒ def get_admin_role(uid) — Получить роль админа. Проверяет обе схемы: суперадмин (БД) и админ (таблица admins).
- ƒ def get_admin_role_by_platform(platform, uid) — Получить роль админа по платформе (max/vk).
- ƒ def list_requests_for_org(org_id, date_from, date_to, status, page, per_page, auto_done_only)
- ƒ def get_upcoming_confirmed(org_id)
- ƒ def mark_reminder_sent(request_id, kind)
- ƒ def increment_reminder_attempt(request_id, kind)
- ƒ def get_pending_for_client_confirm()
- ƒ def mark_client_asked(request_id)
- ƒ def increment_client_ask_attempt(request_id)
- ƒ def set_client_answer(request_id, answer)
- ƒ def get_pending_timeout()
- ƒ def set_broadcast_image(bid, image_id)
- ƒ def list_auto_broadcasts(org_id)
- ƒ def get_auto_broadcast(aid)
- ƒ def create_auto_broadcast(org_id, atype, text, delay_value, image_id)
- ƒ def update_auto_broadcast(aid, text, delay_value, image_id, active)
- ƒ def delete_auto_broadcast(aid)
- ƒ def toggle_auto_broadcast(aid)
- ƒ def log_auto_broadcast(auto_id, user_id, event_ref)
- ƒ def find_visits_for_review_request(org_id, delay_hours) — Находит done-визиты, по которым ещё не запрошен отзыв и прошло >= delay_hours.
- ƒ def mark_review_requested(request_id) — Фиксирует, что по визиту уже отправили запрос на отзыв.
- ƒ def save_review(org_id, user_id, request_id, rating, doctor_id, service_id, comment) — Сохраняет отзыв. UNIQUE(request_id) — повторный вызов ничего не сделает.
- ƒ def get_review_by_request(request_id)
- ƒ def mark_review_admin_notified(review_id)
- ƒ def mark_review_public_link_sent(review_id)
- ƒ def get_client_review_stats(user_id, org_id) — Средний рейтинг, количество, распределение 1..5, последние 5 отзывов.
- ƒ def list_reviews(org_id, rating_filter, doctor_id, rating, limit, offset) — Список отзывов для админки.
- ƒ def count_reviews(org_id)
- ƒ def get_doctor_review_stats(doctor_id, org_id) — Средний рейтинг, распределение, последние отзывы по специалисту.
- ƒ def get_doctors_review_stats_batch(doctor_ids, org_id) — Батч-версия: {doctor_id: {total, avg_rating}}. Для бейджей и списков.
- ƒ def find_revisit_candidates(org_id) — Находит пары (клиент, услуга), которым пора напомнить о повторе.
- ƒ def check_auto_log_revisit(auto_id, user_id, service_id, cooldown_days) — True — уже отправляли по этой (услуге, клиенту) недавно, блокируем.
- ƒ def count_bookings_for_client_before(user_id, org_id, exclude_request_id) — Сколько активных/завершённых записей было у клиента в этой org
- ƒ def get_active_auto_broadcast_by_type(org_id, atype) — Первый активный сценарий указанного типа для организации (или None).
- ƒ def check_auto_log_birthday(auto_id, user_id)
- ƒ def check_auto_log_inactive(auto_id, user_id, last_visit_at, cooldown_days) — True — уже отправляли недавно, блокируем.
- ƒ def check_auto_log_after_visit(auto_id, event_ref)
- ƒ def schedule_broadcast(bid, scheduled_at) — Переводит draft → scheduled с датой.
- ƒ def unschedule_broadcast(bid) — Возвращает scheduled → draft (отмена планирования).
- ƒ def get_scheduled_broadcasts_due(now_iso) — Запланированные, чьё время уже наступило.
- ƒ def get_client_full(user_id, org_id) — Полная карточка клиента + история визитов + агрегаты + услуги/специалисты/предстоящие.
- ƒ def set_client_photo(user_id, upload_id) — Привязывает/отвязывает фото клиента. upload_id=None — убрать фото.
- ƒ def update_client_notes_tags(user_id, notes, tags) — Обновляет заметки и теги. tags — список строк (сохраняется как JSON).
- ƒ def reset_client_no_show(user_id)
- ƒ def get_client_no_show_count(user_id)
- ƒ def update_booking_extended(request_id, new_service_id, new_service_name, new_slots_count, step_min) — Изменяет услугу и/или количество слотов для существующей записи.
- ƒ def move_booking(request_id, new_slot_id) — Переносит заявку на новый слот. Атомарно: освобождает старые слоты,
- ƒ def finalize_move_booking(request_id, new_slot_ids, new_scheduled_at, new_branch_id, new_doctor_id, new_address, new_doctor) — Обновляет history после move_booking и занимает новые слоты.
- ƒ def create_waitlist_entry(org_id, user_id, service_id, date_from, date_to, doctor_id, branch_id, preferred_time, notes, created_by)
- ƒ def get_waitlist_entry(wid)
- ƒ def list_waitlist(org_id, status, service_id, doctor_id, branch_id, limit, offset)
- ƒ def list_active_waitlist_for_user(org_id, user_id)
- ƒ def update_waitlist_entry(wid)
- ƒ def cancel_waitlist_entry(wid)
- ƒ def fulfill_waitlist_entry(wid, request_id)
- ƒ def find_waitlist_matches_for_slot(org_id, slot_id) — Находит активные заявки листа ожидания, подходящие под слот.
- ƒ def mark_waitlist_notified(wid, slot_id)
- ƒ def expire_old_waitlist_entries(org_id) — Помечает expired все активные заявки, у которых date_to < сегодня.
- ƒ def create_slot_offer(org_id, slot_id, user_id, kind, original_request_id, waitlist_id, status)
- ƒ def get_slot_offer(oid)
- ƒ def list_slot_offers_for_slot(slot_id, status)
- ƒ def count_user_offers_since(user_id, kind, since_iso)
- ƒ def update_slot_offer_status(oid, status, error)
- ƒ def mark_other_offers_taken(slot_id, exclude_offer_id) — Все остальные 'sent' по этому слоту → 'taken' (слот уже занят).
- ƒ def _period_bounds(d_from, d_to) — Возвращает (start_str, end_str) для WHERE scheduled_at BETWEEN.
- ƒ def _compute_period_metrics(org_id, d_from, d_to, branch_id, doctor_id)
- ƒ def _top_services(org_id, d_from, d_to, branch_id, doctor_id, limit)
- ƒ def _top_doctors(org_id, d_from, d_to, branch_id, doctor_id, limit)
- ƒ def get_analytics_daily_series(org_id, date_from, date_to, branch_id, doctor_id) — Дневная серия: по каждому дню периода — визиты, выручка, неявки.
- ƒ def get_analytics_summary(org_id, date_from, date_to, branch_id, doctor_id) — Сводка по метрикам за период + сравнение с предыдущим периодом той же длины.
- ƒ def get_analytics_doctor_summary(org_id, doctor_id, date_from, date_to) — Сводка по одному специалисту за период (для модалки в аналитике).
- ƒ def find_backfill_candidates(org_id, slot_id, min_gap_hours, limit) — Кандидаты для backfill.

### `tools/gen_map.py` (293 стр.)
- ƒ def should_skip_file(name: str) -> bool
- ƒ def walk_dirs(root: Path) — os.walk с фильтрацией мусора и сортировкой.
- ƒ def _func_sig(node)
- ƒ def parse_py(path: Path) — Возвращает (items, error). items = [(kind, name, sig, doc, line)]
- ƒ def extract_imports(path: Path) — Внутренние и сторонние импорты (без stdlib).
- ƒ def parse_js_ts(path: Path)
- ƒ def analyze_file(path: Path)
- ƒ def file_lines(p: Path) -> int
- ƒ def build_map(root: Path) -> str
- ƒ def build_summary(root: Path) -> str
- ƒ def main()

---
*Конец карты.*