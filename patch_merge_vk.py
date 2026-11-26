#!/usr/bin/env python3
"""patch_merge_vk.py v2 — склейка phone-дубля с VK-клиентом.

clients не трогаем по user_id (первичный ключ!) — только телефон и удаление дубля.
Для таблиц с уникальным user_id при конфликте приоритет у KEEP.
"""
import sqlite3

DB = "booking.db"
KEEP = "vk:1098777315"
GONE = "phone:+79950653111"

conn = sqlite3.connect(DB)
cur = conn.cursor()

for uid, label in ((KEEP, "KEEP"), (GONE, "GONE")):
    if not cur.execute("SELECT 1 FROM clients WHERE user_id=?", (uid,)).fetchone():
        print(f"Клиент {label} ({uid}) не найден — прерываю.")
        raise SystemExit(1)

tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
moved, deleted = [], []

for t in tables:
    if t == "clients":
        continue
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]
    if "user_id" not in cols:
        continue
    # Уникальность user_id: PK или уникальный индекс из одной колонки user_id.
    pk_cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()
               if r[5]]
    unique_uid = pk_cols == ["user_id"]
    if not unique_uid:
        for idx in cur.execute(f"PRAGMA index_list({t})").fetchall():
            if not idx[2]:
                continue
            icols = [r[2] for r in cur.execute(
                f"PRAGMA index_info({idx[1]})").fetchall()]
            if icols == ["user_id"]:
                unique_uid = True
    has_keep = cur.execute(
        f"SELECT 1 FROM {t} WHERE user_id=? LIMIT 1", (KEEP,)).fetchone()
    has_gone = cur.execute(
        f"SELECT 1 FROM {t} WHERE user_id=? LIMIT 1", (GONE,)).fetchone()
    if unique_uid and has_keep and has_gone:
        n = cur.execute(f"DELETE FROM {t} WHERE user_id=?", (GONE,)).rowcount
        deleted.append(f"{t}: {n} (конфликт уникальности, KEEP важнее)")
    n = cur.execute(
        f"UPDATE {t} SET user_id=? WHERE user_id=?", (KEEP, GONE)).rowcount
    if n:
        moved.append(f"{t}: {n}")

row = cur.execute("SELECT phone FROM clients WHERE user_id=?", (KEEP,)).fetchone()
new_phone = row[0] or GONE
cur.execute("UPDATE clients SET phone=?, org_id=1, updated_at=datetime('now') "
            "WHERE user_id=?", (new_phone, KEEP))
cur.execute("DELETE FROM clients WHERE user_id=?", (GONE,))
conn.commit()
conn.close()

print("Перенесено:", ", ".join(moved) or "ничего")
if deleted:
    print("Удалено при конфликтах:", "; ".join(deleted))
print(f"Телефон VK-клиента: {new_phone}")
print(f"Дубль {GONE} удалён.")
