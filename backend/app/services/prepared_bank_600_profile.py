from app.services import demo_task_bank_service as bank_service

BANK_600_SECTIONS = [
    ("current_oral", "2.1 Вопросы для устного опроса", "oral", 160),
    ("current_practice", "2.1 Практические задания текущего контроля", "practice", 120),
    ("intermediate_credit", "2.2 Вопросы к зачету", "credit", 120),
    ("intermediate_credit_practice", "2.2 Практические задания к зачету", "credit_practice", 80),
    ("diagnostic", "2.3 Итоговая диагностическая работа", "diagnostic", 120),
]
BANK_600_TOTAL = sum(section[3] for section in BANK_600_SECTIONS)


def activate_prepared_bank_600_profile() -> None:
    bank_service.SECTIONS = BANK_600_SECTIONS
    bank_service.TOTAL = BANK_600_TOTAL
    bank_service.MODEL_VERSION = "prepared-system-bank-v4.0-600-context-qwen"
    bank_service.QWEN_BATCH_SIZE = max(getattr(bank_service, "QWEN_BATCH_SIZE", 5), 10)


activate_prepared_bank_600_profile()
