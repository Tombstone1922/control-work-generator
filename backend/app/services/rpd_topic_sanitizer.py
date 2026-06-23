from __future__ import annotations

import re

BAD_TOPIC_FRAGMENTS = {
    "очная",
    "заочная",
    "очно-заочная",
    "занятия",
    "занятие",
    "лекционного",
    "лекционные",
    "семинарского",
    "практической",
    "практические",
    "самостоятельная",
    "самостоятельной",
    "работа",
    "работы",
    "индикатора",
    "достижения",
    "типа",
    "типа / из них",
    "типа / из них в",
    "в форме",
    "форме",
    "подготовки",
    "по дисциплине",
    "по направлению",
    "зачет",
    "экзамен",
    "итого",
    "всего",
}

BAD_MARKERS = (
    "форма обучения",
    "формы обучения",
    "вид учебной деятельности",
    "занятия лекционного",
    "занятия семинарского",
    "самостоятельная работа",
    "промежуточная аттестация",
    "индикатора достижения",
    "типа / из них",
    "в форме подготовки",
    "по дисциплине",
    "направления подготовки",
    "направлению подготовки",
    "учебная неделя",
    "контактная работа",
    "консультации",
    "общая трудоемкость",
    "общая трудоёмкость",
    "академических часах",
    "академические часы",
    "ак.ч",
    "ак. ч",
    "з.е",
    "зачетных единиц",
    "зачётных единиц",
    "трудоемкость дисциплины",
    "трудоёмкость дисциплины",
    "код дисциплины",
    "индекс дисциплины",
    "перечень оценочных средств",
    "рекомендуемых к использованию",
    "формировании оценочных материалов",
)

QUESTION_STARTERS = (
    "что такое",
    "что такое?",
    "какие методы",
    "какие преимущества",
    "как определить",
    "как вы думаете",
    "перечислите",
    "расскажите",
    "объясните",
    "опишите",
    "назовите",
    "приведите",
    "почему",
    "зачем",
    "чем отличается",
    "в чем разница",
    "в чём разница",
    "для чего",
    "что произойдет",
    "что произойдёт",
)

QUESTION_MARKERS = (
    "?",
    "перечислите ",
    "расскажите ",
    "объясните ",
    "опишите ",
    "назовите ",
    "приведите пример",
    "в чем разница",
    "в чём разница",
    "чем отличается",
    "какие ",
    "как ",
    "зачем ",
    "почему ",
)

DEFINITION_CUT_MARKERS = (
    " в процессе изучения темы ",
    " рассматривается ",
    " рассматриваются ",
    " заключается ",
    " заключается в ",
    " осуществляется ",
    " характеризуется ",
    " является ",
    " одним из ",
    " предполагает ",
    " направлена на ",
    " включает ",
    " состоит ",
)

DOMAIN_WORDS = (
    "html", "css", "javascript", "typescript", "react", "vue", "php", "api", "rest", "http", "dom",
    "интерфейс", "интерфейсы", "веб", "web", "программирование", "приложение", "приложений",
    "архитектура", "проект", "проектирование", "информационная", "информационных", "систем",
    "база", "данных", "sql", "компонент", "frontend", "backend", "тестирование", "оптимизация",
)

MODULE_CODE_RE = re.compile(r"^(?:[БB]\s*\.?)?\d+(?:\.\d+){2,}\.?\s*[-–—:]?\s*", re.IGNORECASE)
MODULE_CODE_WITH_LETTER_RE = re.compile(r"^[БB]\s*\.\s*\d+(?:\.\d+)+\s*[-–—:]?\s*", re.IGNORECASE)


def sanitize_rpd_topics(topics: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_topic in topics or []:
        topic = sanitize_rpd_topic(raw_topic)
        if not topic or not is_valid_rpd_topic(topic):
            continue
        key = _norm(topic)
        if key in seen:
            continue
        seen.add(key)
        result.append(topic)
    return result


def sanitize_rpd_topic(value: str) -> str:
    value = _clean(value)
    if not value:
        return ""

    lower_before = value.lower().replace("ё", "е")
    if _looks_like_workload_or_service_line(lower_before):
        return ""

    value = _extract_quoted_title_after_module_code(value) or value
    value = re.sub(r"^(?:тема|раздел)\s*\d+(?:\.\d+)*[.)]?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", value)
    value = MODULE_CODE_WITH_LETTER_RE.sub("", value)
    value = MODULE_CODE_RE.sub("", value)
    value = re.sub(r"^Б\.?\s*\d+(?:\.\d+)+\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+\d+(?:\s+\d+){1,10}$", "", value)
    value = re.sub(r"\s+\|\s*\d+\s*(?:\|\s*\d+\s*)+$", "", value)

    lower = f" {value.lower().replace('ё', 'е')} "
    cut_positions = [lower.find(marker) for marker in DEFINITION_CUT_MARKERS if lower.find(marker) > 0]
    if cut_positions:
        value = value[: min(cut_positions)].strip()

    value = re.sub(r"\b(Лекции|Практические занятия|Лабораторные работы|Самостоятельная работа)\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+Методология\s+создания.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+Обследование\s+информационной\s+системы.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+Структура\s+проекта\s+информационной\s+системы.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+Одним\s+из\s+базовых.*$", "", value, flags=re.IGNORECASE)

    return _clean(value)


def is_valid_rpd_topic(value: str) -> bool:
    value = _clean(value)
    if not value:
        return False
    lower = value.lower().replace("ё", "е")
    if lower in BAD_TOPIC_FRAGMENTS:
        return False
    if any(marker in lower for marker in BAD_MARKERS):
        return False
    if _looks_like_workload_or_service_line(lower):
        return False
    if _looks_like_module_code_line(value):
        return False
    if _looks_like_assessment_question(lower):
        return False
    if re.fullmatch(r"[\d\s.,;/|\\\-–—]+", value):
        return False
    if len(value) < 8 or len(value) > 170:
        return False
    words = re.findall(r"[A-Za-zА-Яа-я0-9+#./-]+", lower)
    if len(words) < 2 and not any(word in lower for word in DOMAIN_WORDS):
        return False
    if words and all(word in BAD_TOPIC_FRAGMENTS for word in words):
        return False
    if len(words) <= 3 and not any(word in lower for word in DOMAIN_WORDS):
        return False
    if lower.endswith(("типа", "форме", "подготовки", "достижения", "индикатора")):
        return False
    return True


def _extract_quoted_title_after_module_code(value: str) -> str:
    if not (MODULE_CODE_RE.match(value) or MODULE_CODE_WITH_LETTER_RE.match(value)):
        return ""
    match = re.search(r"[«\"]([^»\"]{8,140})[»\"]", value)
    return _clean(match.group(1)) if match else ""


def _looks_like_workload_or_service_line(lower: str) -> bool:
    if any(marker in lower for marker in BAD_MARKERS):
        return True
    if re.search(r"\b\d+\s*ак\.?\s*ч\.?\b", lower):
        return True
    if re.search(r"\b\d+\s*(?:час|часа|часов)\b", lower) and any(word in lower for word in ("академ", "трудоем", "трудоём", "объем", "объём")):
        return True
    if re.search(r"\b\d+\s*з\.?\s*е\.?\b", lower):
        return True
    return False


def _looks_like_module_code_line(value: str) -> bool:
    cleaned = _clean(value)
    if re.fullmatch(r"(?:[БB]\s*\.?)?\d+(?:\.\d+){2,}\.?", cleaned, flags=re.IGNORECASE):
        return True
    if re.match(r"^[БB]\s*\.\s*\d+(?:\.\d+)+", cleaned, flags=re.IGNORECASE):
        return True
    return False


def _looks_like_assessment_question(lower: str) -> bool:
    lower = lower.strip()
    if any(lower.startswith(starter) for starter in QUESTION_STARTERS):
        return True
    if "?" in lower:
        return True
    if any(marker in f" {lower} " for marker in QUESTION_MARKERS):
        # Названия тем редко являются прямыми вопросами или императивами. Для РПД такие строки считаем заданиями, а не темами.
        return True
    return False


def _clean(value: str) -> str:
    value = str(value or "").replace("#default#", "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .;:-—|\t\n\r\"«»")


def _norm(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9+#]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
