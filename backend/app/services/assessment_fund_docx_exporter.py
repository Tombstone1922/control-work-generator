from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.assessment_item_validation import AssessmentItemsValidation
from app.schemas import AssessmentFundResponse, AssessmentFundSection, AssessmentItemRead

EXPORT_DIR = Path(__file__).resolve().parents[1] / "storage" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

SPECIAL_SECTION_TYPES = {"competency_matrix", "grading_rubric"}


def export_assessment_fund_to_docx(
    fund: AssessmentFundResponse,
    items: list[AssessmentItemRead],
    validation: AssessmentItemsValidation,
) -> Path:
    document = Document()
    _configure_document(document)
    _add_title_page(document, fund)
    _add_contents(document, fund)
    _add_competency_matrix(document, fund)
    _add_assessment_materials(document, fund, items)
    _add_grading_rubric(document)
    _add_answers_appendix(document, fund, items)
    _add_validation_appendix(document, validation)

    filename = f"fos_{_safe_filename(fund.discipline_name)}_{fund.fund_id[:8]}.docx"
    output_path = EXPORT_DIR / filename
    document.save(output_path)
    return output_path


def _configure_document(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(3)
    section.right_margin = Cm(1.5)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.font.size = Pt(14)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.first_line_indent = Cm(1.25)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for style_name in ("Heading 1", "Heading 2", "Heading 3"):
        style = document.styles[style_name]
        style.font.name = "Times New Roman"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        style.font.size = Pt(14)
        style.font.bold = True
        style.paragraph_format.line_spacing = 1.5
        style.paragraph_format.first_line_indent = Cm(0)
        style.paragraph_format.space_before = Pt(6)
        style.paragraph_format.space_after = Pt(6)


def _add_title_page(document: Document, fund: AssessmentFundResponse) -> None:
    _add_centered(document, "ОЦЕНОЧНЫЕ МАТЕРИАЛЫ", bold=True, size=16, space_before=150)
    _add_centered(document, "ПО ДИСЦИПЛИНЕ", bold=True, size=16)
    _add_centered(document, f"«{fund.discipline_name}»", bold=True, size=16, space_before=18)
    _add_centered(document, "", space_before=24)
    _add_centered(document, "Фонд оценочных средств", bold=True, size=14)
    _add_centered(document, "сформирован на основании рабочей программы дисциплины", size=14)
    _add_centered(document, "", space_before=120)
    _add_centered(document, f"Статус проекта: {_status_label(fund.status)}", size=14)
    _add_centered(document, f"Дата формирования: {datetime.now().strftime('%d.%m.%Y')}", size=14)
    document.add_page_break()


def _add_contents(document: Document, fund: AssessmentFundResponse) -> None:
    _add_heading(document, "СОДЕРЖАНИЕ", level=1, centered=True)
    entries = [
        "1. Перечень компетенций и уровни их сформированности",
        "2. Оценочные материалы для текущего и промежуточного контроля",
    ]
    for section in _enabled_content_sections(fund.sections):
        entries.append(f"   {section.title}")
    entries.extend(
        [
            "3. Критерии выставления оценок",
            "Приложение А. Эталонные ответы и критерии оценивания",
            "Приложение Б. Отчет автоматизированной проверки банка заданий",
        ]
    )
    for entry in entries:
        paragraph = document.add_paragraph(entry)
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    document.add_page_break()


def _add_competency_matrix(document: Document, fund: AssessmentFundResponse) -> None:
    _add_heading(document, "1. Перечень компетенций и уровни их сформированности", level=1)
    _add_body(document, "В разделе приведены компетенции, выявленные в рабочей программе дисциплины, индикаторы их достижения и используемые уровни сформированности.")

    table = document.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    headers = ["Код компетенции", "Содержание компетенции", "Индикаторы достижения", "Уровни сформированности"]
    for index, value in enumerate(headers):
        _set_cell_text(table.rows[0].cells[index], value, bold=True)

    if fund.competencies:
        for competency in fund.competencies:
            row = table.add_row().cells
            _set_cell_text(row[0], competency.code)
            _set_cell_text(row[1], competency.description or "Описание требует уточнения преподавателем.")
            _set_cell_text(row[2], "\n".join(competency.indicators) or "Индикаторы требуют уточнения преподавателем.")
            _set_cell_text(row[3], "\n".join(competency.levels) or "Уровни требуют уточнения преподавателем.")
    else:
        row = table.add_row().cells
        _set_cell_text(row[0], "—")
        _set_cell_text(row[1], "Компетенции не распознаны автоматически.")
        _set_cell_text(row[2], "Требуется ручное заполнение.")
        _set_cell_text(row[3], "Требуется ручное заполнение.")

    document.add_paragraph()


def _add_assessment_materials(
    document: Document,
    fund: AssessmentFundResponse,
    items: list[AssessmentItemRead],
) -> None:
    _add_heading(document, "2. Оценочные материалы для текущего и промежуточного контроля", level=1)
    items_by_section: dict[str, list[AssessmentItemRead]] = defaultdict(list)
    for item in items:
        items_by_section[item.section_code].append(item)

    for section in _enabled_content_sections(fund.sections):
        _add_heading(document, section.title, level=2)
        _add_body(document, section.description)
        section_items = items_by_section.get(section.code, [])
        if not section_items:
            _add_body(document, "Задания для данного раздела пока не сформированы.", italic=True)
            continue

        if section.assessment_type == "diagnostic":
            _add_diagnostic_table(document, section_items)
        else:
            _add_section_items(document, section_items)


def _add_section_items(document: Document, items: list[AssessmentItemRead]) -> None:
    grouped: dict[str, list[AssessmentItemRead]] = defaultdict(list)
    for item in items:
        grouped[item.topic or "Тема не указана"].append(item)

    item_number = 1
    for topic, topic_items in grouped.items():
        _add_heading(document, f"Тема: {topic}", level=3)
        for item in topic_items:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = paragraph.add_run(f"{item_number}. {item.text}")
            run.font.name = "Times New Roman"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
            run.font.size = Pt(14)
            _add_metadata(document, item)
            item_number += 1


def _add_diagnostic_table(document: Document, items: list[AssessmentItemRead]) -> None:
    table = document.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["№", "Формулировка задания", "Эталонный ответ", "Компетенция", "Индикатор"]
    for index, value in enumerate(headers):
        _set_cell_text(table.rows[0].cells[index], value, bold=True)
    for index, item in enumerate(items, start=1):
        row = table.add_row().cells
        _set_cell_text(row[0], str(index))
        _set_cell_text(row[1], item.text)
        _set_cell_text(row[2], item.answer or "Требует уточнения преподавателем.")
        _set_cell_text(row[3], item.competency_code or "—")
        _set_cell_text(row[4], item.indicator or "—")


def _add_metadata(document: Document, item: AssessmentItemRead) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run(
        f"Тема: {item.topic or '—'}; компетенция: {item.competency_code or '—'}; "
        f"уровень сложности: {_difficulty_label(item.difficulty)}."
    )
    run.italic = True
    run.font.size = Pt(12)
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")


def _add_grading_rubric(document: Document) -> None:
    _add_heading(document, "3. Критерии выставления оценок", level=1)
    _add_body(document, "Оценивание результатов выполнения заданий рекомендуется проводить с учетом полноты ответа, корректности примененного способа решения, обоснованности выводов и соответствия результата требованиям задания.")

    table = document.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Уровень", "Оценка", "Обобщенный критерий"]
    for index, value in enumerate(headers):
        _set_cell_text(table.rows[0].cells[index], value, bold=True)
    rows = [
        ("Продвинутый", "Отлично", "Ответ полный и логически выстроенный; решение корректно; выводы обоснованы; существенные ошибки отсутствуют."),
        ("Повышенный", "Хорошо", "Основные положения раскрыты; решение преимущественно корректно; имеются отдельные неточности, не искажающие итоговый результат."),
        ("Пороговый", "Удовлетворительно", "Продемонстрировано базовое понимание материала; решение частично верно; присутствуют ошибки, но основные элементы задания выполнены."),
        ("Недостаточный", "Неудовлетворительно", "Ответ отсутствует либо содержит существенные ошибки; решение не соответствует условию задания; выводы не обоснованы."),
    ]
    for level, mark, criterion in rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], level)
        _set_cell_text(cells[1], mark)
        _set_cell_text(cells[2], criterion)
    document.add_paragraph()


def _add_answers_appendix(
    document: Document,
    fund: AssessmentFundResponse,
    items: list[AssessmentItemRead],
) -> None:
    document.add_page_break()
    _add_heading(document, "Приложение А. Эталонные ответы и критерии оценивания", level=1)
    items_by_section: dict[str, list[AssessmentItemRead]] = defaultdict(list)
    for item in items:
        items_by_section[item.section_code].append(item)

    for section in _enabled_content_sections(fund.sections):
        section_items = items_by_section.get(section.code, [])
        if not section_items:
            continue
        _add_heading(document, section.title, level=2)
        for index, item in enumerate(section_items, start=1):
            _add_body(document, f"{index}. {item.text}", first_line=False)
            _add_body(document, f"Эталонный ответ: {item.answer or 'Требует уточнения преподавателем.'}", first_line=False)
            _add_body(document, "Критерии оценивания:", first_line=False, bold=True)
            criteria = item.criteria or ["Критерии требуют уточнения преподавателем."]
            for criterion in criteria:
                paragraph = document.add_paragraph(criterion, style="List Bullet")
                paragraph.paragraph_format.first_line_indent = Cm(0)
                paragraph.paragraph_format.left_indent = Cm(0.75)
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def _add_validation_appendix(document: Document, validation: AssessmentItemsValidation) -> None:
    document.add_page_break()
    _add_heading(document, "Приложение Б. Отчет автоматизированной проверки банка заданий", level=1)
    _add_body(document, "Отчет сформирован автоматически и предназначен для предварительной проверки полноты банка заданий перед экспертной оценкой преподавателем и методистом.")

    metrics = [
        ("Всего заданий", str(validation.total_items)),
        ("Покрытие тем", f"{validation.topics_coverage_score}%"),
        ("Покрытие компетенций", f"{validation.competencies_coverage_score}%"),
        ("Готовность эталонных ответов", f"{validation.answers_readiness_score}%"),
        ("Готовность критериев оценивания", f"{validation.criteria_readiness_score}%"),
        ("Доля потенциальных дублей", f"{validation.duplicate_rate}%"),
    ]
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_cell_text(table.rows[0].cells[0], "Показатель", bold=True)
    _set_cell_text(table.rows[0].cells[1], "Значение", bold=True)
    for label, value in metrics:
        row = table.add_row().cells
        _set_cell_text(row[0], label)
        _set_cell_text(row[1], value)

    if validation.warnings:
        _add_heading(document, "Предупреждения", level=2)
        for warning in validation.warnings:
            paragraph = document.add_paragraph(warning, style="List Bullet")
            paragraph.paragraph_format.first_line_indent = Cm(0)

    _add_heading(document, "Матрица покрытия тем", level=2)
    coverage = document.add_table(rows=1, cols=4)
    coverage.style = "Table Grid"
    coverage.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Тема", "Количество заданий", "Разделы", "Компетенции"]
    for index, value in enumerate(headers):
        _set_cell_text(coverage.rows[0].cells[index], value, bold=True)
    for row_data in validation.coverage_rows:
        row = coverage.add_row().cells
        sections = "; ".join(f"{key}: {value}" for key, value in row_data.section_counts.items()) or "—"
        _set_cell_text(row[0], row_data.topic)
        _set_cell_text(row[1], str(row_data.total_items))
        _set_cell_text(row[2], sections)
        _set_cell_text(row[3], ", ".join(row_data.competencies) or "—")

    if validation.duplicate_groups:
        _add_heading(document, "Потенциальные дубли", level=2)
        for index, group in enumerate(validation.duplicate_groups, start=1):
            _add_body(document, f"Группа {index}; сходство {round(group.similarity * 100)}%; связанных заданий: {len(group.item_ids)}. Пример формулировки: {group.sample_text}", first_line=False)


def _enabled_content_sections(sections: list[AssessmentFundSection]) -> list[AssessmentFundSection]:
    return [
        section
        for section in sections
        if section.enabled and section.assessment_type not in SPECIAL_SECTION_TYPES
    ]


def _add_heading(document: Document, text: str, level: int, centered: bool = False) -> None:
    paragraph = document.add_heading(text, level=level)
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT


def _add_body(
    document: Document,
    text: str,
    *,
    italic: bool = False,
    bold: bool = False,
    first_line: bool = True,
) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Cm(1.25) if first_line else Cm(0)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = paragraph.add_run(text)
    run.italic = italic
    run.bold = bold
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(14)


def _add_centered(
    document: Document,
    text: str,
    *,
    bold: bool = False,
    size: int = 14,
    space_before: int = 0,
) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.space_before = Pt(space_before)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)


def _set_cell_text(cell, value: str, *, bold: bool = False) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run(value)
    run.bold = bold
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(11)
    _set_cell_margins(cell, top=60, start=80, bottom=60, end=80)


def _set_cell_margins(cell, **kwargs: int) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin in ("top", "start", "bottom", "end"):
        if margin in kwargs:
            node = tc_mar.find(qn(f"w:{margin}"))
            if node is None:
                node = OxmlElement(f"w:{margin}")
                tc_mar.append(node)
            node.set(qn("w:w"), str(kwargs[margin]))
            node.set(qn("w:type"), "dxa")


def _safe_filename(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:80] or "discipline"


def _status_label(status: str) -> str:
    return {
        "draft": "черновик",
        "generated": "сформировано",
        "in_review": "на проверке",
        "revision_required": "требует доработки",
        "approved": "утверждено",
    }.get(status, status)


def _difficulty_label(difficulty: str) -> str:
    return {
        "easy": "базовый",
        "medium": "средний",
        "hard": "повышенный",
    }.get(difficulty, difficulty)
