from datetime import date as _date, timedelta

from storage.db import (
    init_db, db, list_orgs, create_org,
    create_branch, create_doctor, add_slot,
    list_branches, list_doctors,
)

init_db()

orgs = list_orgs()
if not orgs:
    oid = create_org("Тестовая организация")
    print(f"Создана организация #{oid} «Тестовая организация»")
else:
    oid = orgs[0]["id"]
    print(f"Использую существующую организацию #{oid} «{orgs[0]['name']}»")

# услуги
SERVICES = [
    ("eeg",  oid, "ЭЭГ",     1200, "Чистая голова, без лака/геля"),
    ("uzi",  oid, "УЗИ",     1000, "Натощак"),
    ("echo", oid, "ЭХО-КГ",  1500, "Подготовка не требуется"),
]
conn = db()
conn.execute("DELETE FROM services")
conn.executemany(
    "INSERT INTO services (id, org_id, name, price, prep) VALUES (?, ?, ?, ?, ?)",
    SERVICES,
)
conn.commit()
conn.close()
print("OK, услуги добавлены:", len(SERVICES))

# филиал
branches = list_branches(oid)
if not branches:
    bid = create_branch(oid, "Главный офис", "ул. Ленина, 1", "+7 800 000-00-00")
    print(f"Создан филиал #{bid}")
else:
    bid = branches[0]["id"]
    print(f"Использую филиал #{bid} «{branches[0]['name']}»")

# врач
doctors = list_doctors(bid)
if not doctors:
    did = create_doctor(bid, "Иванова И.И.", "Врач функциональной диагностики")
    print(f"Создан врач #{did}")
else:
    did = doctors[0]["id"]
    print(f"Использую врача #{did} «{doctors[0]['name']}»")

# слоты на 14 дней
today = _date.today()
created = 0
for offset in range(14):
    d = today + timedelta(days=offset)
    wd = d.weekday()
    if wd == 6:
        continue
    if wd == 5:
        start, end = 9, 14
    else:
        start, end = 9, 18
    h, m = start, 0
    while h < end:
        add_slot(oid, bid, did, d.isoformat(), f"{h:02d}:{m:02d}")
        created += 1
        m += 30
        if m == 60:
            m = 0
            h += 1

print(f"OK, слотов создано: {created}")
print(f"\nИтого: org_id={oid}, branch_id={bid}, doctor_id={did}")