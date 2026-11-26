import os
from dotenv import load_dotenv

load_dotenv()

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "0"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://boroda-bot.ru")

MAX_API = "https://platform-api2.max.ru"
WEBHOOK_PATH = "/max_booking/api/webhooks"
SCHEDULE_SOURCE = os.getenv("SCHEDULE_SOURCE", "sqlite")
MINI_APP_BOT_USERNAME = os.getenv("MINI_APP_BOT_USERNAME", "")

DB_PATH = os.getenv("DB_PATH", "booking.db")
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads")

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))
UPLOAD_MAX_DIMENSION = int(os.getenv("UPLOAD_MAX_DIMENSION", "1600"))
UPLOAD_JPEG_QUALITY = int(os.getenv("UPLOAD_JPEG_QUALITY", "85"))
ALLOWED_UPLOAD_MIME = (
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
)

MAX_SEND_ATTEMPTS = int(os.getenv("MAX_SEND_ATTEMPTS", "12"))

EVENING_SUMMARY_DEFAULT_HOUR = int(os.getenv("EVENING_SUMMARY_DEFAULT_HOUR", "20"))

# Таймзона по умолчанию (для новых организаций и как fallback)
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")

# Список поддерживаемых таймзон для UI. Ключ — IANA, значение — подпись.
# Можно расширять; валидация идёт через zoneinfo, любые IANA-зоны работают.
SUPPORTED_TIMEZONES = [
    ("Europe/Kaliningrad",   "Калининград (UTC+2)"),
    ("Europe/Moscow",        "Москва (UTC+3)"),
    ("Europe/Volgograd",     "Волгоград (UTC+3)"),
    ("Europe/Astrakhan",     "Астрахань (UTC+4)"),
    ("Europe/Samara",        "Самара (UTC+4)"),
    ("Asia/Yekaterinburg",   "Екатеринбург (UTC+5)"),
    ("Asia/Omsk",            "Омск (UTC+6)"),
    ("Asia/Novosibirsk",     "Новосибирск (UTC+7)"),
    ("Asia/Novokuznetsk",    "Кемерово / Новокузнецк (UTC+7)"),
    ("Asia/Krasnoyarsk",     "Красноярск (UTC+7)"),
    ("Asia/Irkutsk",         "Иркутск (UTC+8)"),
    ("Asia/Yakutsk",         "Якутск (UTC+9)"),
    ("Asia/Vladivostok",     "Владивосток (UTC+10)"),
    ("Asia/Magadan",         "Магадан (UTC+11)"),
    ("Asia/Kamchatka",       "Камчатка (UTC+12)"),
    ("Asia/Almaty",          "Алматы (UTC+5)"),
    ("Asia/Tbilisi",         "Тбилиси (UTC+4)"),
    ("Asia/Baku",            "Баку (UTC+4)"),
    ("Asia/Tashkent",        "Ташкент (UTC+5)"),
    ("Europe/Kiev",          "Киев (UTC+2/3)"),
    ("UTC",                  "UTC (0)"),
]


def is_superadmin(uid):
    return SUPERADMIN_ID > 0 and int(uid) == SUPERADMIN_ID

# Поддерживаемые сервисы карт для построения маршрута.
# Хранится в organizations.settings.map_provider. Дефолт — "both".
MAP_PROVIDERS = [
    ("yandex", "Яндекс.Карты"),
    ("2gis",   "2ГИС"),
    ("both",   "Оба (клиент выберет)"),
]