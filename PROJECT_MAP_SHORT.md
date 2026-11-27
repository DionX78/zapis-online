# PROJECT MAP (SHORT) — max_booking_bot

*Сгенерировано: 2026-11-27 08:24*

## Дерево + размеры + счётчики
```
.env (5 loc)
.gitignore (14 loc)
CHANGELOG.md (16 loc)
PLAN.md (1219 loc)
PROJECT_MAP.md (1342 loc)
PROJECT_MAP_SHORT.md (137 loc)
app.py (74 loc) [1f]
backup_db.sh (26 loc)
booking.db (1203 loc)
config.py (69 loc) [1f]
deploy.sh (151 loc)
init_project.py (696 loc) [2f]
max-bot.service (15 loc)
nginx.conf.snippet (22 loc)
package-lock.json (6 loc)
register_webhook.py (36 loc)
requirements.txt (10 loc)
scan_project.py (273 loc) [7f]
seed.py (75 loc)
core/
  __init__.py (0 loc)
  analytics_export.py (582 loc) [5f]
  auth.py (176 loc) [1c, 10f]
  booking.py (682 loc) [3c, 5f]
  broadcasts.py (880 loc) [23f]
  client_exports.py (657 loc) [3f]
  dispatcher.py (130 loc) [4f]
  geo.py (65 loc) [4f]
  ics.py (107 loc) [4f]
  max_client.py (414 loc) [1c, 9f]
  merge.py (289 loc) [13f]
  messaging.py (383 loc) [15f]
  notify.py (32 loc) [1f]
  notify_ics.py (64 loc) [1f]
  reminders.py (668 loc) [18f]
  schedule_gateway.py (39 loc) [2c, 1f, 8m]
  updates.py (20 loc) [1c]
  uploads.py (67 loc) [1f]
  waitlist.py (1322 loc) [23f]
  channels/
    __init__.py (0 loc)
    base.py (58 loc) [3c, 7m]
    max.py (119 loc) [1c, 1f, 7m]
    registry.py (99 loc) [5f]
    vk.py (281 loc) [1c, 7f, 7m]
    vk_text.py (68 loc) [2f]
  webhook_adapters/
    max.py (75 loc) [2f]
    vk.py (105 loc) [4f]
handlers/
  __init__.py (0 loc)
  admin.py (127 loc) [3f]
  booking.py (403 loc) [11f]
  client_confirm_callbacks.py (154 loc) [2f]
  merge_callbacks.py (26 loc) [1f]
  reminder_callbacks.py (130 loc) [2f]
  report_callbacks.py (97 loc) [1f]
  request_callbacks.py (112 loc) [2f]
  review_callbacks.py (158 loc) [3f]
  start.py (5 loc) [1f]
  superadmin_callbacks.py (193 loc) [4f]
  unsub_callbacks.py (99 loc) [2f]
  visit_callbacks.py (193 loc) [4f]
mini/
  .env.example (1 loc)
  booking.db (0 loc)
  index.html (13 loc)
  package-lock.json (1698 loc)
  package.json (19 loc)
  vite.config.js (16 loc)
  src/
    App.jsx (63 loc) [1f]
    ClientApp.jsx (281 loc) [11f]
    api.js (47 loc) [2f]
    main.jsx (10 loc)
    theme.css (2506 loc)
    admin/
      AdminApp.jsx (274 loc) [4f]
      AnalyticsPage.jsx (487 loc) [12f]
      AuditLogPage.jsx (193 loc) [6f]
      BlockedUsersPage.jsx (102 loc) [4f]
      BroadcastsPage.jsx (1192 loc) [31f]
      ChannelsPage.jsx (536 loc) [9f]
      ClientCardModal.jsx (753 loc) [13f]
      ClientMessageModal.jsx (207 loc) [4f]
      ClientPrivacyModal.jsx (112 loc) [1f]
      ClientsPage.jsx (108 loc) [4f]
      CreateRequestModal.jsx (596 loc) [11f]
      DashboardPage.jsx (212 loc) [3f]
      DirectoriesPage.jsx (1008 loc) [30f]
      DoctorScheduleModal.jsx (491 loc) [12f]
      DoctorServicesModal.jsx (256 loc) [6f]
      DoctorStatsModal.jsx (180 loc) [3f]
      EditRequestModal.jsx (199 loc) [4f]
      MarkVisitModal.jsx (137 loc) [1f]
      MoveRequestModal.jsx (210 loc) [5f]
      RequestsPage.jsx (478 loc) [14f]
      ReviewsPage.jsx (173 loc) [4f]
      SchedulePage.jsx (898 loc) [24f]
      SettingsPage.jsx (900 loc) [5f]
      VisitDetailsModal.jsx (78 loc) [2f]
      WaitlistPage.jsx (571 loc) [12f]
      adminApi.js (442 loc) [3f]
    components/
      CalendarGrid.jsx (86 loc) [4f]
      DoctorPicker.jsx (79 loc)
      PhoneForm.jsx (241 loc) [3f]
      ServiceList.jsx (115 loc) [1f]
      Success.jsx (20 loc)
      TimeGrid.jsx (189 loc) [6f]
      WaitlistForm.jsx (146 loc) [4f]
      WaitlistPage.jsx (201 loc) [8f]
routers/
  __init__.py (0 loc)
  admin_bots.py (592 loc) [4c, 13f]
  admin_broadcasts.py (466 loc) [19f]
  admin_core.py (242 loc) [9f]
  admin_directories.py (1172 loc) [39f]
  admin_requests.py (1660 loc) [32f]
  admin_reviews.py (89 loc) [2f]
  admin_settings.py (160 loc) [3f]
  admin_uploads.py (169 loc) [3f]
  mini_app.py (595 loc) [12f]
  webhook.py (100 loc) [4f]
  webhook_vk.py (170 loc) [4f]
storage/
  __init__.py (0 loc)
  db.py (5704 loc) [225f]
tools/
  gen_map.py (293 loc) [11f]
```

*Полная карта с сигнатурами: `PROJECT_MAP.md`.*