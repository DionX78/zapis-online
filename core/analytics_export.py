"""Сборка и отправка файлов аналитики (CSV/XLSX/PDF).

Вызывается из:
- routers.admin_core (admin_analytics_export) — по кнопке «📥 Экспорт» в админке
- handlers.report_callbacks — по кнопкам «📊 ...» из вечерней сводки

Функция generate_and_send_analytics делает всё «под ключ»: собирает
данные, формирует файл, отправляет в чат admin_uid, чистит временный
файл при успехе. Возвращает словарь с результатом.
"""
import asyncio
import logging
import uuid as _uuid
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path as _Path

import config
from core.channels.base import UserBlocked
from core.messaging import send_to_client_with_file_raw, upload_file_for_client
from storage.db import (
    get_analytics_summary, get_analytics_daily_series, get_org,
    save_uploaded_image_full, delete_uploaded_image_file, log_audit,
)

log = logging.getLogger(__name__)


# ==================== Сборка контента ====================

def analytics_export_filename(prefix, fmt, date_from, date_to):
    ext = {"csv": "csv", "xlsx": "xlsx", "pdf": "pdf"}[fmt]
    return f"{prefix}_{date_from}_{date_to}.{ext}"


def build_analytics_csv(data):
    import csv as _csv
    buf = StringIO()
    buf.write("\ufeff")
    w = _csv.writer(buf, delimiter=";", lineterminator="\n")

    period = data["period"]
    prev = data["previous_period"]
    cur = data["current"]
    prev_m = data["previous"]
    delta = data["delta"]

    w.writerow(["Период", f"{period['date_from']} — {period['date_to']}", f"{period['days']} дн."])
    w.writerow(["Предыдущий период", f"{prev['date_from']} — {prev['date_to']}"])
    w.writerow([])

    w.writerow(["Показатель", "Текущий", "Предыдущий", "Δ, %"])
    def row(label, cur_v, prev_v, d_v):
        w.writerow([label, cur_v, prev_v, "" if d_v is None else d_v])

    row("Всего записей", cur["total"], prev_m["total"], delta.get("total_pct"))
    row("Пришли", cur["done"], prev_m["done"], delta.get("done_pct"))
    row("Выручка, ₽", cur["revenue"], prev_m["revenue"], delta.get("revenue_pct"))
    row("Средний чек (визит), ₽", cur["avg_check_per_visit"], prev_m["avg_check_per_visit"], delta.get("avg_check_pct"))
    row("Средняя выручка с клиента, ₽", cur["avg_revenue_per_client"], prev_m["avg_revenue_per_client"], None)
    row("Средняя цена услуги, ₽", cur["avg_service_price"], prev_m["avg_service_price"], None)
    row("Неявки, %", cur["no_show_pct"], prev_m["no_show_pct"], delta.get("no_show_pct_pp"))
    row("Загрузка слотов, %", cur["load_pct"], prev_m["load_pct"], delta.get("load_pct_pp"))
    row("Уникальных клиентов", cur["unique_clients"], prev_m["unique_clients"], None)
    row("Новых клиентов", cur["new_clients"], prev_m["new_clients"], delta.get("new_clients_pct"))
    row("Постоянных клиентов", cur["returning_clients"], prev_m["returning_clients"], None)
    row("Возвращаемость, %", cur["returning_rate_pct"], prev_m["returning_rate_pct"], None)
    w.writerow([])

    w.writerow(["Топ услуг"])
    w.writerow(["Услуга", "Визитов", "Выручка, ₽"])
    for it in data.get("top_services") or []:
        w.writerow([it["name"], it["count"], it["revenue"]])
    w.writerow([])

    w.writerow(["Топ специалистов"])
    w.writerow(["Специалист", "Визитов", "Выручка, ₽"])
    for it in data.get("top_doctors") or []:
        w.writerow([it["name"], it["count"], it["revenue"]])

    return buf.getvalue().encode("utf-8")


def build_analytics_xlsx(data):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import BarChart, Reference
    from openpyxl.worksheet.page import PageMargins

    wb = Workbook()

    title_font = Font(name="Calibri", bold=True, size=16, color="2E5F8A")
    section_font = Font(name="Calibri", bold=True, size=12, color="2E5F8A")
    label_font = Font(name="Calibri", bold=True, size=10)
    value_font = Font(name="Calibri", size=10)
    header_font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
    group_font = Font(name="Calibri", bold=True, size=10, color="2E5F8A")

    title_fill = PatternFill("solid", fgColor="E3F0FB")
    group_fill = PatternFill("solid", fgColor="E3F0FB")
    header_fill = PatternFill("solid", fgColor="2E5F8A")
    zebra_fill = PatternFill("solid", fgColor="F7FAFD")
    good_fill = PatternFill("solid", fgColor="E3F5E9")
    bad_fill = PatternFill("solid", fgColor="FDECEC")

    thin = Side(border_style="thin", color="D9E6F2")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    period = data["period"]
    prev = data["previous_period"]
    cur = data["current"]
    prev_m = data["previous"]
    delta = data["delta"]

    ws = wb.active
    ws.title = "Сводка"

    org_name = (data.get("org_name") or "").strip() or "Организация"

    ws.merge_cells("A1:D1")
    c = ws["A1"]
    c.value = org_name
    c.font = title_font
    c.fill = title_fill
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:D2")
    c = ws["A2"]
    c.value = f"📊 Аналитика · {period['date_from']} — {period['date_to']} ({period['days']} дн.) · сравнение с {prev['date_from']} — {prev['date_to']}"
    c.font = value_font
    c.fill = title_fill
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 20

    headers = ["Показатель", "Текущий", "Предыдущий", "Δ"]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border

    metrics = [
        ("Всего записей", cur["total"], prev_m["total"], delta.get("total_pct"), False),
        ("Пришли", cur["done"], prev_m["done"], delta.get("done_pct"), False),
        ("Выручка, ₽", cur["revenue"], prev_m["revenue"], delta.get("revenue_pct"), False),
        ("Средний чек (визит), ₽", cur["avg_check_per_visit"], prev_m["avg_check_per_visit"], delta.get("avg_check_pct"), False),
        ("Средняя выручка с клиента, ₽", cur["avg_revenue_per_client"], prev_m["avg_revenue_per_client"], None, False),
        ("Средняя цена услуги, ₽", cur["avg_service_price"], prev_m["avg_service_price"], None, False),
        ("Неявки, %", cur["no_show_pct"], prev_m["no_show_pct"], delta.get("no_show_pct_pp"), True),
        ("Загрузка слотов, %", cur["load_pct"], prev_m["load_pct"], delta.get("load_pct_pp"), False),
        ("Уникальных клиентов", cur["unique_clients"], prev_m["unique_clients"], None, False),
        ("Новых клиентов", cur["new_clients"], prev_m["new_clients"], delta.get("new_clients_pct"), False),
        ("Постоянных клиентов", cur["returning_clients"], prev_m["returning_clients"], None, False),
        ("Возвращаемость, %", cur["returning_rate_pct"], prev_m["returning_rate_pct"], None, False),
    ]

    row = 5
    for i, (label, cv, pv, dv, invert) in enumerate(metrics):
        ws.cell(row=row, column=1, value=label).font = label_font
        ws.cell(row=row, column=2, value=cv).font = value_font
        ws.cell(row=row, column=3, value=pv).font = value_font
        dcell = ws.cell(row=row, column=4)
        if dv is not None:
            arrow = "↑" if dv > 0 else ("↓" if dv < 0 else "→")
            suffix = " п.п." if invert and label.startswith("Неявки") or label.startswith("Загрузка") else "%"
            dcell.value = f"{arrow} {abs(dv):.1f}{suffix}"
            good = (dv < 0) if invert else (dv > 0)
            bad = (dv > 0) if invert else (dv < 0)
            if good:
                dcell.fill = good_fill
            elif bad:
                dcell.fill = bad_fill
        else:
            dcell.value = ""
        dcell.font = value_font
        dcell.alignment = Alignment(horizontal="center")
        for col in range(1, 5):
            ws.cell(row=row, column=col).border = border
            if i % 2 == 1:
                ws.cell(row=row, column=col).fill = zebra_fill
        row += 1

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    c = ws.cell(row=row, column=1, value="🏆 Топ услуг")
    c.font = section_font
    c.fill = group_fill
    row += 1
    for col, h in enumerate(["Услуга", "Визитов", "Выручка, ₽", ""], start=1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
        c.border = border
    row += 1
    for it in data.get("top_services") or []:
        ws.cell(row=row, column=1, value=it["name"]).font = value_font
        ws.cell(row=row, column=2, value=it["count"]).font = value_font
        ws.cell(row=row, column=3, value=it["revenue"]).font = value_font
        for col in range(1, 5):
            ws.cell(row=row, column=col).border = border
        row += 1

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    c = ws.cell(row=row, column=1, value="👤 Топ специалистов")
    c.font = section_font
    c.fill = group_fill
    row += 1
    for col, h in enumerate(["Специалист", "Визитов", "Выручка, ₽", ""], start=1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
        c.border = border
    row += 1
    for it in data.get("top_doctors") or []:
        ws.cell(row=row, column=1, value=it["name"]).font = value_font
        ws.cell(row=row, column=2, value=it["count"]).font = value_font
        ws.cell(row=row, column=3, value=it["revenue"]).font = value_font
        for col in range(1, 5):
            ws.cell(row=row, column=col).border = border
        row += 1

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 16

    ws2 = wb.create_sheet("По дням")

    ws2.merge_cells("A1:D1")
    c = ws2["A1"]
    c.value = "📈 Динамика по дням"
    c.font = title_font
    c.fill = title_fill
    ws2.row_dimensions[1].height = 24

    for col, h in enumerate(["Дата", "Пришли", "Неявки", "Выручка, ₽"], start=1):
        c = ws2.cell(row=3, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")
        c.border = border

    series = data.get("daily_series") or []
    row = 4
    for s in series:
        ws2.cell(row=row, column=1, value=s["date"]).font = value_font
        ws2.cell(row=row, column=2, value=s["done"]).font = value_font
        ws2.cell(row=row, column=3, value=s["no_show"]).font = value_font
        ws2.cell(row=row, column=4, value=s["revenue"]).font = value_font
        for col in range(1, 5):
            ws2.cell(row=row, column=col).border = border
        row += 1

    if series:
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Динамика по дням"
        chart.y_axis.title = "Выручка, ₽"
        chart.x_axis.title = "Дата"

        data_ref = Reference(ws2, min_col=4, min_row=3, max_row=3 + len(series))
        cats_ref = Reference(ws2, min_col=1, min_row=4, max_row=3 + len(series))
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats_ref)
        chart.height = 9
        chart.width = 20
        ws2.add_chart(chart, "F3")

    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 10
    ws2.column_dimensions["C"].width = 10
    ws2.column_dimensions["D"].width = 16

    for sheet in (ws, ws2):
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        sheet.oddHeader.center.text = "Аналитика"
        sheet.oddHeader.center.size = 10
        sheet.oddHeader.center.font = "Calibri,Bold"
        sheet.oddFooter.center.text = "Стр. &P из &N"
        sheet.oddFooter.center.size = 8

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def build_analytics_pdf(data):
    import os
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    font_name = "Helvetica"
    bold_name = "Helvetica-Bold"
    for reg, bold, p_reg, p_bold in (
        ("CustomFont", "CustomFont-Bold",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("CustomFont", "CustomFont-Bold",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ):
        if os.path.exists(p_reg):
            try:
                pdfmetrics.registerFont(TTFont(reg, p_reg))
                font_name = reg
                if os.path.exists(p_bold):
                    pdfmetrics.registerFont(TTFont(bold, p_bold))
                    bold_name = bold
                    try:
                        pdfmetrics.registerFontFamily(
                            reg, normal=reg, bold=bold, italic=reg, boldItalic=bold,
                        )
                    except Exception:
                        pass
                break
            except Exception:
                pass

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="Аналитика",
    )

    title_style = ParagraphStyle("title", fontName=bold_name, fontSize=18, leading=22,
                                 textColor=colors.HexColor("#2E5F8A"))
    subtitle = ParagraphStyle("sub", fontName=font_name, fontSize=10, leading=13,
                              textColor=colors.HexColor("#555555"))
    section = ParagraphStyle("section", fontName=bold_name, fontSize=12, leading=15,
                             textColor=colors.HexColor("#2E5F8A"), spaceBefore=10, spaceAfter=6)
    normal = ParagraphStyle("n", fontName=font_name, fontSize=9, leading=11)
    bold_small = ParagraphStyle("bs", fontName=bold_name, fontSize=9, leading=11)

    period = data["period"]
    prev = data["previous_period"]
    cur = data["current"]
    prev_m = data["previous"]
    delta = data["delta"]

    elements = []

    org_name = (data.get("org_name") or "").strip() or "Организация"
    elements.append(Paragraph(org_name, title_style))
    elements.append(Paragraph(
        f"📊 Аналитика · {period['date_from']} — {period['date_to']} ({period['days']} дн.) · "
        f"сравнение с {prev['date_from']} — {prev['date_to']}",
        subtitle,
    ))
    elements.append(Spacer(1, 10))

    def fmt_delta(dv, invert=False, pp=False):
        if dv is None:
            return "—"
        arrow = "↑" if dv > 0 else ("↓" if dv < 0 else "→")
        suffix = " п.п." if pp else "%"
        return f"{arrow} {abs(dv):.1f}{suffix}"

    rows = [[
        Paragraph("Показатель", bold_small),
        Paragraph("Текущий", bold_small),
        Paragraph("Предыдущий", bold_small),
        Paragraph("Δ", bold_small),
    ]]
    metrics = [
        ("Всего записей", cur["total"], prev_m["total"], delta.get("total_pct"), False, False),
        ("Пришли", cur["done"], prev_m["done"], delta.get("done_pct"), False, False),
        ("Выручка, ₽", cur["revenue"], prev_m["revenue"], delta.get("revenue_pct"), False, False),
        ("Средний чек (визит), ₽", cur["avg_check_per_visit"], prev_m["avg_check_per_visit"], delta.get("avg_check_pct"), False, False),
        ("Средняя выручка с клиента, ₽", cur["avg_revenue_per_client"], prev_m["avg_revenue_per_client"], None, False, False),
        ("Средняя цена услуги, ₽", cur["avg_service_price"], prev_m["avg_service_price"], None, False, False),
        ("Неявки, %", cur["no_show_pct"], prev_m["no_show_pct"], delta.get("no_show_pct_pp"), True, True),
        ("Загрузка слотов, %", cur["load_pct"], prev_m["load_pct"], delta.get("load_pct_pp"), False, True),
        ("Уникальных клиентов", cur["unique_clients"], prev_m["unique_clients"], None, False, False),
        ("Новых клиентов", cur["new_clients"], prev_m["new_clients"], delta.get("new_clients_pct"), False, False),
        ("Постоянных клиентов", cur["returning_clients"], prev_m["returning_clients"], None, False, False),
        ("Возвращаемость, %", cur["returning_rate_pct"], prev_m["returning_rate_pct"], None, False, True),
    ]
    for label, cv, pv, dv, invert, pp in metrics:
        rows.append([
            Paragraph(label, normal),
            Paragraph(str(cv), normal),
            Paragraph(str(pv), normal),
            Paragraph(fmt_delta(dv, invert, pp), normal),
        ])
    t = Table(rows, colWidths=[90 * mm, 40 * mm, 40 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5F8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E6F2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFD")]),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)

    if data.get("top_services"):
        elements.append(Paragraph("🏆 Топ услуг", section))
        rows = [[
            Paragraph("Услуга", bold_small),
            Paragraph("Визитов", bold_small),
            Paragraph("Выручка, ₽", bold_small),
        ]]
        for it in data["top_services"]:
            rows.append([
                Paragraph(it["name"], normal),
                Paragraph(str(it["count"]), normal),
                Paragraph(f"{it['revenue']:,}".replace(",", " "), normal),
            ])
        t = Table(rows, colWidths=[130 * mm, 40 * mm, 40 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F0FB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2E5F8A")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E6F2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFD")]),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(t)

    if data.get("top_doctors"):
        elements.append(Paragraph("👤 Топ специалистов", section))
        rows = [[
            Paragraph("Специалист", bold_small),
            Paragraph("Визитов", bold_small),
            Paragraph("Выручка, ₽", bold_small),
        ]]
        for it in data["top_doctors"]:
            rows.append([
                Paragraph(it["name"], normal),
                Paragraph(str(it["count"]), normal),
                Paragraph(f"{it['revenue']:,}".replace(",", " "), normal),
            ])
        t = Table(rows, colWidths=[130 * mm, 40 * mm, 40 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F0FB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2E5F8A")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E6F2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFD")]),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(t)

    doc.build(elements)
    return buf.getvalue()


# ==================== Оркестрация ====================

async def generate_and_send_analytics(
    org_id: int,
    admin_uid: int,
    date_from: str,
    date_to: str,
    fmt: str,
    branch_id: int | None = None,
    doctor_id: int | None = None,
    caption_prefix: str = "📊 **Аналитика**",
) -> dict:
    """Генерирует аналитику за период, отправляет в чат admin_uid.

    Возвращает dict с полями:
      ok, filename, format, url, full_url, sent_to_chat, send_error
    """
    fmt = (fmt or "xlsx").lower().strip()
    if fmt not in ("csv", "xlsx", "pdf"):
        raise ValueError("format must be csv, xlsx or pdf")

    data = await asyncio.to_thread(
        get_analytics_summary, org_id, date_from, date_to, branch_id, doctor_id,
    )
    _org = get_org(org_id)
    data["org_name"] = _org["name"] if _org else ""

    if fmt == "xlsx":
        series = await asyncio.to_thread(
            get_analytics_daily_series, org_id, date_from, date_to, branch_id, doctor_id,
        )
        data["daily_series"] = series

    if fmt == "csv":
        content = build_analytics_csv(data)
        mime = "text/csv"
        ext = "csv"
    elif fmt == "xlsx":
        content = build_analytics_xlsx(data)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        content = build_analytics_pdf(data)
        mime = "application/pdf"
        ext = "pdf"

    filename = analytics_export_filename("analytics", fmt, date_from, date_to)

    rel_dir = str(org_id)
    abs_dir = _Path(config.UPLOADS_DIR) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    local_name = f"{_uuid.uuid4().hex}.{ext}"
    abs_path = abs_dir / local_name
    abs_path.write_bytes(content)
    rel_path = f"{rel_dir}/{local_name}"

    uid_img, public_token = save_uploaded_image_full(
        token=None, file_path=rel_path, mime_type=mime,
        original_filename=filename, file_size=len(content),
        org_id=org_id, uploaded_by=admin_uid,
    )
    public_url = f"/max_booking/api/upload/{public_token}"
    full_url = config.WEBHOOK_BASE_URL.rstrip("/") + public_url

    caption = (
        f"{caption_prefix}\n\n"
        f"📅 {date_from} — {date_to}\n"
        f"📄 {filename} ({len(content) // 1024} KB)"
    )

    sent_ok = False
    send_err = None
    try:
        token = await upload_file_for_client(
            admin_uid, content, filename=filename, mime=mime,
            upload_type="file",
        )
        await send_to_client_with_file_raw(int(admin_uid), caption, token, fmt="markdown")
        sent_ok = True
    except UserBlocked:
        send_err = "blocked"
    except Exception as e:
        log.error("analytics send to %s failed: %s", admin_uid, e)
        send_err = str(e)[:200]

    if sent_ok:
        try:
            delete_uploaded_image_file(uid_img)
            public_url = None
            full_url = None
        except Exception as e:
            log.warning("analytics cleanup failed: %s", e)

    log_audit(
        org_id=org_id, user_id=admin_uid, action=f"analytics_export_{fmt}",
        entity_type="analytics", entity_id=None,
        payload={"filename": filename, "size": len(content),
                 "date_from": date_from, "date_to": date_to,
                 "sent_to_chat": sent_ok},
    )

    return {
        "ok": True,
        "filename": filename,
        "format": fmt,
        "url": public_url,
        "full_url": full_url,
        "sent_to_chat": sent_ok,
        "send_error": send_err,
    }