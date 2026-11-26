import logging

import httpx

log = logging.getLogger(__name__)

_cache = {}


async def _shorten(url):
    """Сокращает URL через clck.ru; при ошибке возвращает как есть."""
    if len(url) <= 45:
        return url
    if url in _cache:
        return _cache[url]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post("https://clck.ru/--", data={"url": url})
        s = (r.text or "").strip()
        if s.startswith("http"):
            _cache[url] = s
            return s
    except Exception as e:
        log.debug("clck.ru shorten failed: %s", e)
    return url


async def vk_text(text):
    """VK не рендерит Markdown. Готовим текст:
    **жирный** -> текст, [подпись](url) -> подпись: короткая ссылка."""
    if not text:
        return text
    text = text.replace("**", "")
    out = []
    i = 0
    while True:
        j = text.find("[", i)
        if j < 0:
            out.append(text[i:])
            break
        k = text.find("](", j)
        if k < 0:
            out.append(text[i:])
            break
        e = text.find(")", k)
        if e < 0:
            out.append(text[i:])
            break
        label = text[j + 1:k]
        url = text[k + 2:e]
        out.append(text[i:j])
        out.append(label + ": " + (await _shorten(url)))
        i = e + 1
    text = "".join(out)
    words = []
    changed = False
    for w in text.split(" "):
        if w.startswith("http"):
            core = w.rstrip(").,;")
            tail = w[len(core):]
            if len(core) > 45:
                words.append((await _shorten(core)) + tail)
                changed = True
                continue
        words.append(w)
    if changed:
        text = " ".join(words)
    return text
