from pathlib import Path

from docx import Document

from app.schemas import GenerationResponse


EXPORT_DIR = Path(__file__).resolve().parents[1] / "storage" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def export_generation_to_docx(generation: GenerationResponse) -> Path:
    document = Document()
    document.add_heading("Контрольная работа", level=1)
    document.add_paragraph(f"Идентификатор сеанса генерации: {generation.session_id}")
    document.add_paragraph(f"Идентификатор РПД: {generation.program_id}")

    for variant in generation.variants:
        document.add_heading(f"Вариант {variant.variant_number}", level=2)
        for index, question in enumerate(variant.questions, start=1):
            document.add_paragraph(
                f"{index}. {question.text}\n"
                f"Тема: {question.topic}\n"
                f"Тип: {question.type}; уровень сложности: {question.difficulty}"
            )

    document.add_heading("Отчет качества", level=2)
    document.add_paragraph(f"Покрытие тем: {generation.quality_report.topic_coverage}")
    document.add_paragraph(f"Доля дублей: {generation.quality_report.duplicate_rate}")
    document.add_paragraph(f"Всего заданий: {generation.quality_report.total_questions}")
    for rec in generation.quality_report.recommendations:
        document.add_paragraph(rec, style="List Bullet")

    output_path = EXPORT_DIR / f"control_work_{generation.session_id}.docx"
    document.save(output_path)
    return output_path
