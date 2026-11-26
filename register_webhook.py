"""Регистрация webhook в MAX.
Запуск: python3 register_webhook.py [url]
"""
import sys

import truststore
truststore.inject_into_ssl()

import httpx
import config

DEFAULT_URL = config.WEBHOOK_BASE_URL + config.WEBHOOK_PATH
URL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
ENDPOINT = config.MAX_API + "/subscriptions"

headers = {
    "Authorization": config.MAX_BOT_TOKEN,
    "Content-Type": "application/json",
}
body = {
    "url": URL,
    "update_types": ["message_created", "message_callback", "bot_started"],
}
if config.WEBHOOK_SECRET:
    body["secret"] = config.WEBHOOK_SECRET

print("POST", ENDPOINT)
r = httpx.post(ENDPOINT, json=body, headers=headers, timeout=20)
print("Status:", r.status_code)
print("Body:", r.text)

print()
print("GET", ENDPOINT)
r2 = httpx.get(ENDPOINT, headers=headers, timeout=20)
print("Status:", r2.status_code)
print("Body:", r2.text)
