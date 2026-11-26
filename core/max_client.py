"""Клиент MAX API с обработкой ошибок и retry."""
import asyncio
import logging

import httpx
import truststore

truststore.inject_into_ssl()

import config

log = logging.getLogger(__name__)


class MaxUserBlocked(Exception):
    """Клиент заблокировал бота (403/404). Воркеры ловят это исключение
    и не считают попытку провальной — просто помечают отправленным."""
    pass


async def send_message(user_id: int, text: str, buttons: list = None, fmt: str = None, max_retries: int = 3):
    """
    Отправляет сообщение через MAX API.
    Возвращает dict с ответом или бросает исключение при ошибке.
    Автоматически повторяет при 429.
    """
    if not config.MAX_BOT_TOKEN:
        raise Exception("MAX_BOT_TOKEN не задан")

    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    if fmt:
        payload["format"] = fmt
    if buttons:
        payload["attachments"] = [{
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }]

    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    config.MAX_API + "/messages",
                    params={"user_id": user_id},
                    json=payload,
                    headers=headers,
                )

                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 1))
                    log.warning("Rate limit for user %s, retry after %ss", user_id, retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if r.status_code in (403, 404):
                    log.info("User %s blocked bot or chat not found (HTTP %s)", user_id, r.status_code)
                    raise MaxUserBlocked(f"User {user_id} blocked bot")

                if 200 <= r.status_code < 300:
                    result = r.json()
                    log.info("Message sent to %s: %s", user_id, r.status_code)
                    return result

                last_error = Exception(f"MAX API returned {r.status_code}: {r.text[:200]}")
                log.error("send_message to %s failed: %s %s", user_id, r.status_code, r.text[:200])
                break

        except MaxUserBlocked:
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = Exception(f"Network error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            break
        except Exception as e:
            last_error = e
            break

    if last_error:
        raise last_error
    raise Exception("Unknown error")


async def send_message_with_image(user_id: int, text: str, image_token: str, buttons: list = None, fmt: str = None, max_retries: int = 3):
    """Отправляет сообщение с картинкой."""
    if not config.MAX_BOT_TOKEN:
        raise Exception("MAX_BOT_TOKEN не задан")

    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "attachments": [
            {
                "type": "image",
                "payload": {"token": image_token},
            }
        ],
    }
    if fmt:
        payload["format"] = fmt
    if buttons:
        payload["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        })

    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    config.MAX_API + "/messages",
                    params={"user_id": user_id},
                    json=payload,
                    headers=headers,
                )

                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 1))
                    await asyncio.sleep(retry_after)
                    continue

                if r.status_code in (403, 404):
                    log.info("User %s blocked bot", user_id)
                    raise MaxUserBlocked(f"User {user_id} blocked bot")

                if 200 <= r.status_code < 300:
                    result = r.json()
                    log.info("Message with image sent to %s", user_id)
                    return result

                if r.status_code >= 400:
                    try:
                        err_data = r.json()
                        code = err_data.get("code", "")
                        if "attachment.not.ready" in code or "attachment.file.not_processed" in code:
                            if attempt < max_retries - 1:
                                wait = 2 ** attempt
                                log.warning("Image not ready for user %s, retry in %ss", user_id, wait)
                                await asyncio.sleep(wait)
                                continue
                    except ValueError:
                        pass

                last_error = Exception(f"MAX API returned {r.status_code}: {r.text[:200]}")
                log.error("send_message_with_image to %s failed: %s", user_id, r.status_code)
                break

        except MaxUserBlocked:
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = Exception(f"Network error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            break
        except Exception as e:
            last_error = e
            break

    if last_error:
        raise last_error
    raise Exception("Unknown error")


def _extract_token(data: dict) -> str | None:
    """Устойчивый парсер ответа MAX при загрузке файла.
    Поддерживает варианты:
      {"token": "..."}
      {"file": {"token": "..."}}
      {"file": {"<key>": {"token": "..."}}}
      {"files": {...}}
      {"photos": {...}}
    """
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("token"), str) and data["token"]:
        return data["token"]
    for key in ("file", "files", "photos", "data"):
        block = data.get(key)
        if not block:
            continue
        if isinstance(block, dict):
            if isinstance(block.get("token"), str) and block["token"]:
                return block["token"]
            first = next(iter(block.values()), None)
            if isinstance(first, dict) and isinstance(first.get("token"), str) and first["token"]:
                return first["token"]
    return None


async def upload_file(content, filename: str, mime: str = "text/calendar",
                     upload_type: str = "file", max_retries: int = 2) -> str:
    """Загружает файл в MAX, возвращает token для использования в attachment.

    upload_type: "file" (по умолчанию) или "image".
    content может быть str (будет UTF-8) или bytes.
    """
    if not config.MAX_BOT_TOKEN:
        raise Exception("MAX_BOT_TOKEN не задан")

    data_bytes = content.encode("utf-8") if isinstance(content, str) else content
    headers = {"Authorization": config.MAX_BOT_TOKEN}

    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1) Получить upload URL
                r = await client.post(
                    config.MAX_API + "/uploads",
                    params={"type": upload_type},
                    headers=headers,
                )
                if r.status_code != 200:
                    raise Exception(f"MAX /uploads вернул {r.status_code}: {r.text[:200]}")
                data = r.json()
                upload_url = data.get("url")
                if not upload_url:
                    raise Exception(f"В ответе /uploads нет url: {data}")

                # 2) Загрузить файл
                files = {"data": (filename, data_bytes, mime)}
                r2 = await client.post(upload_url, files=files)
                if r2.status_code not in (200, 201):
                    raise Exception(f"Загрузка в S3 вернула {r2.status_code}: {r2.text[:200]}")

                data2 = r2.json()
                log.info("upload_file response: %s", data2)

                token = _extract_token(data2)
                if not token:
                    raise Exception(f"Не удалось извлечь token: {data2}")
                return token
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            break

    raise last_error or Exception("upload_file failed")


async def send_message_with_file(user_id: int, text: str, file_token: str,
                                  buttons: list = None, fmt: str = None,
                                  max_retries: int = 5):
    """Отправляет сообщение с файлом-вложением (attachment type=file).
    Обрабатывает attachment.not.ready — retry с нарастающей задержкой."""
    if not config.MAX_BOT_TOKEN:
        raise Exception("MAX_BOT_TOKEN не задан")

    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "attachments": [
            {"type": "file", "payload": {"token": file_token}},
        ],
    }
    if fmt:
        payload["format"] = fmt
    if buttons:
        payload["attachments"].append({
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        })

    last_error = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    config.MAX_API + "/messages",
                    params={"user_id": user_id},
                    json=payload,
                    headers=headers,
                )

                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 1))
                    await asyncio.sleep(retry_after)
                    continue

                if r.status_code in (403, 404):
                    log.info("User %s blocked bot", user_id)
                    raise MaxUserBlocked(f"User {user_id} blocked bot")

                if 200 <= r.status_code < 300:
                    log.info("Message with file sent to %s", user_id)
                    return r.json()

                # attachment.not.ready — файл ещё обрабатывается на сервере MAX
                if r.status_code >= 400:
                    try:
                        err_data = r.json()
                        code = err_data.get("code", "")
                        if "attachment.not.ready" in code:
                            if attempt < max_retries - 1:
                                wait = 2 ** attempt  # 1, 2, 4, 8 сек
                                log.warning(
                                    "File not ready for %s (attempt %d/%d), retry in %ss",
                                    user_id, attempt + 1, max_retries, wait,
                                )
                                await asyncio.sleep(wait)
                                continue
                    except ValueError:
                        pass

                last_error = Exception(f"MAX API returned {r.status_code}: {r.text[:200]}")
                log.error("send_message_with_file to %s failed: %s", user_id, r.status_code)
                break

        except MaxUserBlocked:
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = Exception(f"Network error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            break
        except Exception as e:
            last_error = e
            break

    if last_error:
        raise last_error
    raise Exception("Unknown error")


async def edit_message(message_id: str, text: str, buttons: list = None, fmt: str = None):
    """Редактирует сообщение."""
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    payload = {"text": text, "notify": False}
    if fmt:
        payload["format"] = fmt
    if buttons:
        payload["attachments"] = [{
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }]
    else:
        payload["attachments"] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.put(
                config.MAX_API + "/messages",
                params={"message_id": message_id},
                json=payload,
                headers=headers,
            )
            log.info("Message edited: %s", r.status_code)
            return r.json() if 200 <= r.status_code < 300 else {}
    except Exception as e:
        log.warning("edit_message failed: %s", e)
        return {}


async def delete_message(message_id: str):
    """Удаляет сообщение."""
    headers = {"Authorization": config.MAX_BOT_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.delete(
                config.MAX_API + "/messages",
                params={"message_id": message_id},
                headers=headers,
            )
            log.info("Message deleted: %s", r.status_code)
            return r.json() if 200 <= r.status_code < 300 else {}
    except Exception as e:
        log.warning("delete_message failed: %s", e)
        return {}


async def set_commands(commands: list):
    """Регистрирует команды бота."""
    headers = {
        "Authorization": config.MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.patch(
                config.MAX_API + "/me/commands",
                json={"commands": commands},
                headers=headers,
            )
            log.info("Commands set: %s", r.status_code)
    except Exception as e:
        log.error("set_commands error: %s", e)


async def get_me():
    """Возвращает информацию о боте."""
    headers = {"Authorization": config.MAX_BOT_TOKEN}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(config.MAX_API + "/me", headers=headers)
        return r.json()