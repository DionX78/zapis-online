#!/usr/bin/env python3
with open("PLAN.md", "r", encoding="utf-8") as f:
    src = f.read()
ENTRY = """## 2026-11-26
- E4.3 (VK): фикс `attachment` — вложения доходят; `upload_file` с `user_id`; рассылки с картинками до VK-клиентов доходят.
- VK-клиенты: org_id из бота вебхука, автозаполнение ФИО/пол/ДР из `users.get`, создание при первом сообщении.
- Багфиксы: `int(user_id)` в отправках (booking/reminders/waitlist/notify_ics/request_callbacks), `asyncio` в booking, текст «заблокировал бота в МАХ» → канало-нейтральный.
- Багфикс формы записи: ввод телефона больше не сбрасывает выбранного клиента; бэкенд пишет телефон выбранному клиенту.
- Склейка дубля phone:+79950653111 → vk:1098777315 (история перенесена).
- Бейдж каналов (MAX/VK/MAX+VK) в списке и карточке.
- E4.5 (ред. 2): склейка по телефону с подтверждением из обоих каналов; фото из VK в карточку клиента.

"""
anchor = "## 2026-02-05"
if "## 2026-11-26" in src:
    print("PLAN.md: уже пропатчен")
elif anchor in src:
    src = src.replace(anchor, ENTRY + anchor, 1)
    with open("PLAN.md", "w", encoding="utf-8") as f:
        f.write(src)
    print("PLAN.md: запись добавлена в начало журнала изменений")
else:
    print("PLAN.md: якорь не найден — вставь запись вручную выше '## 2026-02-05'")
