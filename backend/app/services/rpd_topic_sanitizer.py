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

    value = re.sub(r"^(?:тема|раздел)\s*\d+(?:\.\d+)*[.)]?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", value)
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


def _clean(value: str) -> str:
    value = str(value or "").replace("#default#", "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .;:-—|\t\n\r")


def _norm(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9+#]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
