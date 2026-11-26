"""Утилиты для загружаемых файлов: ресайз и компрессия изображений.

Вынесено из app.py, т.к. используется в нескольких местах
(фото клиентов, фото специалистов, вложения в сообщения, рассылки).
"""
from io import BytesIO

import config


def _process_upload_image(content: bytes, mime_type: str) -> tuple[bytes, str, str]:
    """Ресайз + компрессия. Возвращает (content, mime_type, ext).
    При ошибке — возвращает оригинал без изменений.

    - GIF — без изменений (не ломаем анимацию).
    - Если размер ≤ 1600 px и файл < 1.5 MB — без изменений.
    - Иначе ресайз до 1600 px. Прозрачность → PNG, всё остальное → JPEG q=85.
    """
    from PIL import Image, ImageOps

    if mime_type == "image/gif":
        return content, mime_type, "gif"

    try:
        img = Image.open(BytesIO(content))
        img = ImageOps.exif_transpose(img)
    except Exception:
        ext = "jpg"
        if mime_type == "image/png":
            ext = "png"
        elif mime_type == "image/webp":
            ext = "webp"
        return content, mime_type, ext

    max_dim = config.UPLOAD_MAX_DIMENSION
    quality = config.UPLOAD_JPEG_QUALITY
    original_size = len(content)

    need_resize = img.width > max_dim or img.height > max_dim
    need_process = need_resize or original_size > 1_500_000

    if not need_process:
        ext = "jpg"
        if mime_type == "image/png":
            ext = "png"
        elif mime_type == "image/webp":
            ext = "webp"
        return content, mime_type, ext

    if need_resize:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )

    out = BytesIO()
    if has_alpha:
        if img.mode == "P":
            img = img.convert("RGBA")
        img.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png", "png"
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue(), "image/jpeg", "jpg"