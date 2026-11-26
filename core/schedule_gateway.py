"""Шлюз расписания.
Бот всегда спрашивает слоты через этот модуль, а не напрямую из БД.
Позже сюда добавятся адаптеры: Excel, Google Sheets, CRM.
"""
from storage import db


class ScheduleGateway:
    def get_dates(self, org_id, limit_days=14):
        raise NotImplementedError

    def get_slots(self, org_id, date):
        raise NotImplementedError

    def book(self, slot_id, request_id=None):
        raise NotImplementedError

    def release(self, slot_id):
        raise NotImplementedError


class SQLiteScheduleGateway(ScheduleGateway):
    def get_dates(self, org_id, limit_days=14):
        return db.list_dates_with_slots(org_id, limit_days)

    def get_slots(self, org_id, date):
        return db.list_free_slots(org_id, date)

    def book(self, slot_id, request_id=None):
        return db.book_slot(slot_id, request_id)

    def release(self, slot_id):
        return db.release_slot(slot_id)


def get_gateway() -> ScheduleGateway:
    import config
    # Заглушка: пока всегда SQLite. Позже — выбор по config.SCHEDULE_SOURCE.
    return SQLiteScheduleGateway()