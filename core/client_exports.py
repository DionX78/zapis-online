"""Сборка файлов экспорта карточки клиента: CSV / XLSX / PDF.

Вызывается из routers.admin_requests (admin_client_export_file).
Все зависимости (openpyxl, reportlab) импортируются локально
внутри функций — чтобы модуль быстро грузился.
"""
from datetime import datetime
from io import BytesIO

from storage.db import get_service  # noqa: F401 — на будущее, может понадобиться


def build_client_export_csv(data, client):
    from io import StringIO
    import csv as _csv
    buf = StringIO()
    buf.write("\ufeff")
    w = _csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["Тип", "ID", "Дата и время", "Услуга", "Специалист", "Статус",
                "Сумма, ₽", "Способ оплаты", "Слотов", "Авто"])
    status_map = {
        "pending": "ожидает", "confirmed": "подтверждена",
        "cancelled": "отменена", "done": "пришёл", "no_show": "не пришёл",
    }
    for r in (data.get("upcoming") or []):
        w.writerow([
            "предстоящий", r["id"], r["scheduled_at"], r["service_name"] or "",
            r["doctor"] or "", status_map.get(r["status"], r["status"]),
            "", "", r["slots_count"] or 1, "",
        ])
    for r in data["history"]:
        w.writerow([
            "история", r["id"], r["scheduled_at"], r["service_name"] or "",
            r["doctor"] or "", status_map.get(r["status"], r["status"]),
            r["actual_amount"] if r["actual_amount"] is not None else "",
            r["payment_method"] or "",
            r["slots_count"] or 1,
            "да" if r["done_auto"] else "",
        ])
    return buf.getvalue().encode("utf-8")


def build_client_export_xlsx(data, client, for_client=False):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.page import PageMargins
    from openpyxl.worksheet.properties import PageSetupProperties, Outline
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    title_font = Font(name="Calibri", bold=True, size=16, color="2E5F8A")
    name_font = Font(name="Calibri", bold=True, size=14, color="1F2D3A")
    label_font = Font(name="Calibri", bold=True, size=10)
    value_font = Font(name="Calibri", size=10)
    section_font = Font(name="Calibri", bold=True, size=12, color="2E5F8A")
    group_font = Font(name="Calibri", bold=True, size=10, color="2E5F8A")
    total_font = Font(name="Calibri", bold=True, size=11)

    title_fill = PatternFill("solid", fgColor="E3F0FB")
    group_fill = PatternFill("solid", fgColor="E3F0FB")
    upcoming_fill = PatternFill("solid", fgColor="FFF4D9")
    total_fill = PatternFill("solid", fgColor="FFF4D9")
    zebra_fill = PatternFill("solid", fgColor="F7FAFD")

    thin = Side(border_style="thin", color="D9E6F2")
    thick = Side(border_style="medium", color="2E5F8A")
    border_thin = Border(left=thin, right=thin, top=thin, bottom=thin)
    border_upcoming = Border(
        left=Side(border_style="thin", color="F0DFA3"),
        right=Side(border_style="thin", color="F0DFA3"),
        top=Side(border_style="thin", color="F0DFA3"),
        bottom=Side(border_style="thin", color="F0DFA3"),
    )

    fio = " ".join(p for p in [client["last_name"], client["first_name"], client["middle_name"]] if p).strip() or str(client["user_id"])
    org_name = data.get("org_name") or ""
    gender_label = "—"
    if client["gender"] == "male":
        gender_label = "Мужской"
    elif client["gender"] == "female":
        gender_label = "Женский"

    _agg = data.get("aggregates")
    agg = dict(_agg) if _agg else {}
    visits_done = agg.get("visits_done") or 0
    visits_no_show = agg.get("visits_no_show") or 0
    total_revenue = agg.get("total_revenue") or 0
    last_done = agg.get("last_done_at") or "—"

    status_map = {
        "pending": "ожидает", "confirmed": "подтверждена",
        "cancelled": "отменена", "done": "пришёл", "no_show": "не пришёл",
    }

    ws = wb.active
    ws.title = "Карточка"

    header_title = "Ваши визиты" if for_client else "Карточка клиента"
    header_subtitle = org_name if for_client else fio

    ws.merge_cells("A1:F1")
    c = ws["A1"]
    c.value = header_title
    c.font = title_font
    c.fill = title_fill
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:F2")
    c = ws["A2"]
    c.value = header_subtitle
    c.font = name_font
    c.fill = title_fill
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 22

    if for_client:
        profile = [
            ("ФИО", fio),
            ("Телефон", client["phone"] or "—"),
            ("Дата рождения", client["birth_date"] or "—"),
            ("Пол", gender_label),
            ("Любимый специалист", data.get("favorite_doctor_name") or "—"),
            ("Последний визит", str(last_done)),
            ("Всего визитов", str(visits_done)),
            ("Общая выручка", f"{total_revenue} ₽"),
        ]
    else:
        consent = "не дано"
        if client["consent_152fz"]:
            consent = f"да ({client['consent_given_at'] or ''})"
        profile = [
            ("Телефон", client["phone"] or "—"),
            ("Дата рождения", client["birth_date"] or "—"),
            ("Пол", gender_label),
            ("Любимый специалист", data.get("favorite_doctor_name") or "—"),
            ("Последний визит", str(last_done)),
            ("Согласие 152-ФЗ", consent),
            ("Всего визитов", str(visits_done)),
            ("Неявок", str(visits_no_show)),
            ("Общая выручка", f"{total_revenue} ₽"),
        ]

    row = 4
    for label, value in profile:
        lc = ws.cell(row=row, column=1, value=label)
        lc.font = label_font
        lc.fill = PatternFill("solid", fgColor="F5F9FC")
        lc.alignment = Alignment(vertical="center")
        vc = ws.cell(row=row, column=2, value=value)
        vc.font = value_font
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        row += 1

    upcoming = data.get("upcoming") or []
    if upcoming:
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        uc = ws.cell(row=row, column=1, value="📅 Предстоящие визиты")
        uc.font = section_font
        uc.fill = upcoming_fill
        uc.alignment = Alignment(horizontal="left", vertical="center")
        row += 1

        up_headers = ["Дата и время", "Услуга", "Специалист", "Статус", "Слотов", ""]
        for col, h in enumerate(up_headers, start=1):
            cc = ws.cell(row=row, column=col, value=h)
            cc.font = group_font
            cc.fill = upcoming_fill
            cc.alignment = Alignment(horizontal="center", vertical="center")
            cc.border = border_upcoming
        row += 1
        for v in upcoming:
            vals = [
                str(v["scheduled_at"] or ""),
                str(v["service_name"] or ""),
                str(v["doctor"] or "—"),
                status_map.get(v["status"], v["status"]),
                v["slots_count"] or 1,
                "",
            ]
            for col, val in enumerate(vals, start=1):
                cc = ws.cell(row=row, column=col, value=val)
                cc.font = value_font
                cc.border = border_upcoming
                if col in (4, 5):
                    cc.alignment = Alignment(horizontal="center")
            row += 1

    if data["history"]:
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        hc = ws.cell(row=row, column=1, value="📋 История визитов")
        hc.font = section_font
        hc.fill = title_fill
        hc.alignment = Alignment(horizontal="left", vertical="center")
        row += 1

        by_service = {}
        for r in data["history"]:
            sname = r["service_name"] or "—"
            by_service.setdefault(sname, []).append(r)

        for sname, visits in by_service.items():
            service_amount = sum((v["actual_amount"] or 0) for v in visits if v["status"] == "done")
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
            gc = ws.cell(row=row, column=1, value=f"📂 {sname} · {len(visits)} визит(ов)")
            gc.font = group_font
            gc.fill = group_fill
            gc.alignment = Alignment(horizontal="left", vertical="center")
            sa = ws.cell(row=row, column=6, value=service_amount if service_amount else None)
            sa.font = group_font
            sa.fill = group_fill
            sa.alignment = Alignment(horizontal="right")
            sa.number_format = '#,##0 "₽"'
            for col in range(1, 7):
                ws.cell(row=row, column=col).border = border_thin
            row += 1

            visit_headers = ["Дата и время", "Услуга", "Специалист", "Статус", "Сумма", "Оплата"]
            for col, h in enumerate(visit_headers, start=1):
                cc = ws.cell(row=row, column=col, value=h)
                cc.font = Font(name="Calibri", bold=True, size=9, color="2E5F8A")
                cc.fill = PatternFill("solid", fgColor="F5F9FC")
                cc.alignment = Alignment(horizontal="center", vertical="center")
                cc.border = border_thin
            row += 1

            for i, v in enumerate(visits):
                amt = v["actual_amount"]
                vals = [
                    str(v["scheduled_at"] or ""),
                    str(v["service_name"] or ""),
                    str(v["doctor"] or "—"),
                    status_map.get(v["status"], v["status"]),
                    int(amt) if amt is not None else None,
                    str(v["payment_method"] or ""),
                ]
                for col, val in enumerate(vals, start=1):
                    cc = ws.cell(row=row, column=col, value=val)
                    cc.font = value_font
                    cc.border = border_thin
                    if i % 2 == 1:
                        cc.fill = zebra_fill
                    if col == 4:
                        cc.alignment = Alignment(horizontal="center")
                    if col == 5:
                        cc.alignment = Alignment(horizontal="right")
                        cc.number_format = '#,##0 "₽"'
                row += 1

        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        total_cell = ws.cell(row=row, column=1, value="Итого выручка (по завершённым визитам)")
        total_cell.font = total_font
        total_cell.fill = total_fill
        total_cell.alignment = Alignment(horizontal="right", vertical="center")
        total_amt = ws.cell(row=row, column=6, value=total_revenue)
        total_amt.font = total_font
        total_amt.fill = total_fill
        total_amt.alignment = Alignment(horizontal="right")
        total_amt.number_format = '#,##0 "₽"'
        for col in range(1, 7):
            ws.cell(row=row, column=col).border = Border(
                left=thick, right=thick, top=thick, bottom=thick,
            )

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 15
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 14
    ws.print_area = f"A1:F{row}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)
    ws.oddHeader.center.text = header_title
    ws.oddHeader.center.size = 10
    ws.oddHeader.center.font = "Calibri,Bold"
    ws.oddFooter.center.text = "Стр. &P из &N"
    ws.oddFooter.center.size = 8

    ws2 = wb.create_sheet("История визитов")
    ws2.sheet_properties.outlinePr = Outline(summaryBelow=False, summaryRight=False)

    ws2.merge_cells("A1:I1")
    c = ws2["A1"]
    c.value = f"История визитов · {fio}"
    c.font = title_font
    c.fill = title_fill
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws2.row_dimensions[1].height = 22

    headers = ["ID", "Дата и время", "Услуга", "Специалист", "Статус",
               "Сумма, ₽", "Способ оплаты", "Слотов", "Авто"]
    header_fill = PatternFill("solid", fgColor="2E5F8A")
    header_font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
    header_border = Border(left=thin, right=thin, top=thick, bottom=thick)
    for col, h in enumerate(headers, start=1):
        c = ws2.cell(row=2, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = header_border

    tree_service = {}
    for r in data["history"]:
        sname = r["service_name"] or "—"
        dname = r["doctor"] or "—"
        st = status_map.get(r["status"], r["status"])
        tree_service.setdefault(sname, {}).setdefault(dname, {}).setdefault(st, []).append(r)

    def _group_amount(rows):
        return sum((v["actual_amount"] or 0) for v in rows if v["status"] == "done")

    def _write_group_header(row_idx, level, title, total_amount):
        ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=8)
        hc = ws2.cell(row=row_idx, column=1, value=title)
        hc.font = group_font
        hc.fill = group_fill if level == 0 else (PatternFill("solid", fgColor="EEF6FC") if level == 1 else PatternFill("solid", fgColor="F7FAFD"))
        hc.alignment = Alignment(horizontal="left", vertical="center", indent=level * 2)
        amt = ws2.cell(row=row_idx, column=9, value=(total_amount if total_amount else None))
        amt.font = group_font
        amt.fill = group_fill if level == 0 else (PatternFill("solid", fgColor="EEF6FC") if level == 1 else PatternFill("solid", fgColor="F7FAFD"))
        amt.alignment = Alignment(horizontal="right", vertical="center")
        amt.number_format = '#,##0 "₽"'
        for col in range(1, 10):
            ws2.cell(row=row_idx, column=col).border = border_thin
        if level > 0:
            ws2.row_dimensions[row_idx].outlineLevel = level
        ws2.row_dimensions[row_idx].hidden = False

    def _write_visit_row(row_idx, r, i, indent_level=3):
        ws2.cell(row=row_idx, column=1, value=r["id"])
        ws2.cell(row=row_idx, column=2, value=str(r["scheduled_at"] or ""))
        ws2.cell(row=row_idx, column=3, value=str(r["service_name"] or ""))
        ws2.cell(row=row_idx, column=4, value=str(r["doctor"] or "—"))
        ws2.cell(row=row_idx, column=5, value=status_map.get(r["status"], r["status"]))
        amt = r["actual_amount"]
        ws2.cell(row=row_idx, column=6, value=int(amt) if amt is not None else None)
        ws2.cell(row=row_idx, column=7, value=str(r["payment_method"] or ""))
        ws2.cell(row=row_idx, column=8, value=r["slots_count"] or 1)
        ws2.cell(row=row_idx, column=9, value="да" if r["done_auto"] else "")
        for col in range(1, 10):
            cc = ws2.cell(row=row_idx, column=col)
            cc.font = value_font
            cc.border = border_thin
            if i % 2 == 1:
                cc.fill = zebra_fill
        ws2.cell(row=row_idx, column=6).alignment = Alignment(horizontal="right")
        ws2.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")
        ws2.cell(row=row_idx, column=8).alignment = Alignment(horizontal="center")
        ws2.row_dimensions[row_idx].outlineLevel = indent_level
        ws2.row_dimensions[row_idx].hidden = False

    row = 3
    visit_counter = 0
    grand_total = 0

    for sname in sorted(tree_service.keys(), key=lambda s: (-len(tree_service[s]), s)):
        by_spec = tree_service[sname]
        all_visits = [v for sp in by_spec.values() for st in sp.values() for v in st]
        service_amount = _group_amount(all_visits)
        service_count = len(all_visits)
        grand_total += service_amount
        _write_group_header(row, 0, f"📂 {sname} · {service_count} визит(ов)", service_amount)
        row += 1

        for dname in sorted(by_spec.keys(), key=lambda d: (-len(by_spec[d]), d)):
            by_status = by_spec[dname]
            spec_visits = [v for st in by_status.values() for v in st]
            spec_amount = _group_amount(spec_visits)
            spec_count = len(spec_visits)
            _write_group_header(row, 1, f"👤 {dname} · {spec_count} визит(ов)", spec_amount)
            row += 1

            for st in sorted(by_status.keys()):
                visits = by_status[st]
                st_amount = _group_amount(visits)
                st_count = len(visits)
                _write_group_header(row, 2, f"● {st} · {st_count}", st_amount)
                row += 1

                for v in visits:
                    _write_visit_row(row, v, visit_counter, indent_level=3)
                    visit_counter += 1
                    row += 1

    if data["history"]:
        sum_row = row
        ws2.merge_cells(start_row=sum_row, start_column=1, end_row=sum_row, end_column=8)
        total_cell = ws2.cell(row=sum_row, column=1, value="Итого выручка (по завершённым визитам)")
        total_cell.font = total_font
        total_cell.fill = total_fill
        total_cell.alignment = Alignment(horizontal="right", vertical="center")
        total_amt = ws2.cell(row=sum_row, column=9, value=grand_total)
        total_amt.font = total_font
        total_amt.fill = total_fill
        total_amt.alignment = Alignment(horizontal="right")
        total_amt.number_format = '#,##0 "₽"'
        for col in range(1, 10):
            ws2.cell(row=sum_row, column=col).border = Border(
                left=thick, right=thick, top=thick, bottom=thick,
            )

    col_widths = [6, 20, 30, 22, 15, 14, 15, 8, 6]
    for i, w in enumerate(col_widths, start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    last_row = row
    ws2.print_area = f"A1:I{last_row}"
    ws2.page_setup.orientation = "landscape"
    ws2.page_setup.fitToWidth = 1
    ws2.page_setup.fitToHeight = 0
    ws2.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws2.page_margins = PageMargins(left=0.3, right=0.3, top=0.5, bottom=0.5)
    ws2.print_title_rows = "2:2"
    ws2.oddHeader.center.text = f"История визитов · {fio}"
    ws2.oddHeader.center.size = 10
    ws2.oddHeader.center.font = "Calibri,Bold"
    ws2.oddFooter.center.text = "Стр. &P из &N"
    ws2.oddFooter.center.size = 8

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def build_client_export_pdf(data, client, for_client=False):
    import os
    from reportlab.lib.pagesizes import A4
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm,
                            title="Ваши визиты" if for_client else "Карточка клиента")

    title_style = ParagraphStyle("title", fontName=bold_name, fontSize=18, leading=22,
                                 textColor=colors.HexColor("#2E5F8A"))
    name_style = ParagraphStyle("name", fontName=bold_name, fontSize=14, leading=18,
                                 textColor=colors.HexColor("#1F2D3A"))
    section_style = ParagraphStyle("section", fontName=bold_name, fontSize=12, leading=15,
                                   textColor=colors.HexColor("#2E5F8A"), spaceBefore=10, spaceAfter=6)
    normal = ParagraphStyle("n", fontName=font_name, fontSize=9.5, leading=12)
    small = ParagraphStyle("s", fontName=font_name, fontSize=8.5, leading=11,
                          textColor=colors.HexColor("#555555"))
    bold_small = ParagraphStyle("bs", fontName=bold_name, fontSize=8.5, leading=11)
    bold_normal = ParagraphStyle("bn", fontName=bold_name, fontSize=9.5, leading=12)

    fio = " ".join(p for p in [client["last_name"], client["first_name"], client["middle_name"]] if p).strip() or str(client["user_id"])
    org_name = data.get("org_name") or ""

    elements = []

    if for_client:
        header_title = "Ваши визиты"
        header_subtitle = org_name
    else:
        header_title = "Карточка клиента"
        header_subtitle = fio

    header_table = Table(
        [[Paragraph(header_title, title_style)],
         [Paragraph(header_subtitle, name_style) if header_subtitle else Paragraph("&nbsp;", normal)]],
        colWidths=[180*mm],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E3F0FB")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("LINEBELOW", (0, 1), (-1, 1), 0.8, colors.HexColor("#B8D4EF")),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))

    gender_label = "—"
    if client["gender"] == "male":
        gender_label = "Мужской"
    elif client["gender"] == "female":
        gender_label = "Женский"

    _agg = data.get("aggregates")
    agg = dict(_agg) if _agg else {}
    visits_done = agg.get("visits_done") or 0
    visits_no_show = agg.get("visits_no_show") or 0
    total_revenue = agg.get("total_revenue") or 0
    last_done = agg.get("last_done_at") or "—"

    if for_client:
        profile_rows = [
            [Paragraph("ФИО:", bold_normal), Paragraph(fio, normal),
             Paragraph("Телефон:", bold_normal), Paragraph(client["phone"] or "—", normal)],
            [Paragraph("Дата рождения:", bold_normal), Paragraph(client["birth_date"] or "—", normal),
             Paragraph("Пол:", bold_normal), Paragraph(gender_label, normal)],
            [Paragraph("Любимый специалист:", bold_normal), Paragraph(data.get("favorite_doctor_name") or "—", normal),
             Paragraph("Последний визит:", bold_normal), Paragraph(str(last_done), normal)],
            [Paragraph("Всего визитов:", bold_normal), Paragraph(str(visits_done), normal),
             Paragraph("Общая выручка:", bold_normal), Paragraph(f"{total_revenue} ₽", normal)],
        ]
    else:
        consent = "не дано"
        if client["consent_152fz"]:
            consent = f"да ({client['consent_given_at'] or ''})"
        profile_rows = [
            [Paragraph("Телефон:", bold_normal), Paragraph(client["phone"] or "—", normal),
             Paragraph("Дата рождения:", bold_normal), Paragraph(client["birth_date"] or "—", normal)],
            [Paragraph("Пол:", bold_normal), Paragraph(gender_label, normal),
             Paragraph("Любимый специалист:", bold_normal), Paragraph(data.get("favorite_doctor_name") or "—", normal)],
            [Paragraph("Последний визит:", bold_normal), Paragraph(str(last_done), normal),
             Paragraph("Согласие 152-ФЗ:", bold_normal), Paragraph(consent, normal)],
            [Paragraph("Визитов:", bold_normal), Paragraph(str(visits_done), normal),
             Paragraph("Неявок:", bold_normal), Paragraph(str(visits_no_show), normal)],
            [Paragraph("Общая выручка:", bold_normal), Paragraph(f"{total_revenue} ₽", normal),
             Paragraph("Экспорт:", bold_normal), Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M"), normal)],
        ]

    profile_table = Table(profile_rows, colWidths=[35*mm, 55*mm, 40*mm, 50*mm])
    profile_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E5EDF5")),
    ]))
    elements.append(profile_table)

    status_map = {
        "pending": "ожидает", "confirmed": "подтверждена",
        "cancelled": "отменена", "done": "пришёл", "no_show": "не пришёл",
    }

    upcoming = data.get("upcoming") or []
    if upcoming:
        elements.append(Paragraph("Предстоящие визиты", section_style))
        up_rows = [[
            Paragraph("Дата", bold_small),
            Paragraph("Услуга", bold_small),
            Paragraph("Специалист", bold_small),
            Paragraph("Статус", bold_small),
            Paragraph("Слотов", bold_small),
        ]]
        for v in upcoming:
            up_rows.append([
                Paragraph(str(v["scheduled_at"]), small),
                Paragraph(str(v["service_name"] or ""), small),
                Paragraph(str(v["doctor"] or "—"), small),
                Paragraph(status_map.get(v["status"], v["status"]), small),
                Paragraph(str(v["slots_count"] or 1), small),
            ])
        up_t = Table(up_rows, colWidths=[35*mm, 60*mm, 45*mm, 25*mm, 15*mm])
        up_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF4D9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#8B5A00")),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#F0DFA3")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#F0B429")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (4, 1), (4, -1), "CENTER"),
        ]))
        elements.append(up_t)

    elements.append(Paragraph("История визитов", section_style))

    by_service = {}
    for r in data["history"]:
        sname = r["service_name"] or "—"
        by_service.setdefault(sname, []).append(r)

    for sname, visits in by_service.items():
        total_service = sum((v["actual_amount"] or 0) for v in visits if v["status"] == "done")

        rows = [[
            Paragraph(f"<b>{sname}</b> · {len(visits)} визит(ов)", bold_small),
            "", "", "",
            Paragraph(f"<b>{total_service} ₽</b>", bold_small),
        ], [
            Paragraph("<b>Дата</b>", bold_small),
            Paragraph("<b>Услуга</b>", bold_small),
            Paragraph("<b>Специалист</b>", bold_small),
            Paragraph("<b>Статус</b>", bold_small),
            Paragraph("<b>Сумма</b>", bold_small),
        ]]
        for v in visits:
            rows.append([
                Paragraph(str(v["scheduled_at"]), small),
                Paragraph(str(v["service_name"] or ""), small),
                Paragraph(str(v["doctor"] or "—"), small),
                Paragraph(status_map.get(v["status"], v["status"]), small),
                Paragraph(f"{v['actual_amount']} ₽" if v["actual_amount"] is not None else "—", small),
            ])

        t = Table(rows, colWidths=[35*mm, 55*mm, 40*mm, 25*mm, 25*mm])
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (3, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F0FB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2E5F8A")),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F5F9FC")),
            ("ALIGN", (4, 0), (4, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E6F2")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#B8D4EF")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 6))

    if not by_service:
        elements.append(Paragraph("Визитов пока нет.", small))

    doc.build(elements)
    return buf.getvalue()