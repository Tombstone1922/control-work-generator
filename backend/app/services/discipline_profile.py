from __future__ import annotations

from dataclasses import replace

from app.services.rpd_analyzer import RpdAnalysisResult


DOMAIN_PROFILES = {
    "history_russia": {
        "label": "История России",
        "keywords": ["история россии", "история", "отечественная история", "российская история"],
        "topics": [
            "Древняя Русь и формирование российской государственности",
            "Московское государство в XV–XVII веках",
            "Российская империя в XVIII–XIX веках",
            "Россия в начале XX века: революции, реформы и общественные процессы",
            "Советское государство: основные этапы развития",
            "Великая Отечественная война и послевоенное развитие СССР",
            "Россия в конце XX — начале XXI века",
            "Историческая память, источники и методы исторического анализа",
        ],
        "outcomes": [
            "Знать основные этапы и закономерности исторического развития России.",
            "Уметь анализировать исторические события, источники и причинно-следственные связи.",
            "Владеть навыками аргументированного изложения исторической позиции.",
        ],
        "task_focus": "исторический анализ, причинно-следственные связи, работа с источниками, периодизация",
    },
    "databases": {
        "label": "Базы данных",
        "keywords": ["база данных", "базы данных", "субд", "sql", "реляцион", "database"],
        "topics": [
            "Понятие базы данных и системы управления базами данных",
            "Реляционная модель данных",
            "Проектирование концептуальной и логической модели данных",
            "Нормализация отношений и функциональные зависимости",
            "Язык SQL: выборка, фильтрация, сортировка и агрегация данных",
            "Соединения таблиц и вложенные запросы",
            "Ограничения целостности, ключи и индексы",
            "Транзакции, безопасность и администрирование баз данных",
        ],
        "outcomes": [
            "Знать принципы построения реляционных баз данных и основные возможности SQL.",
            "Уметь проектировать структуру базы данных и формировать SQL-запросы.",
            "Владеть навыками нормализации схемы данных и проверки целостности данных.",
        ],
        "task_focus": "ER-моделирование, нормализация, SQL-запросы, ограничения целостности",
    },
    "programming": {
        "label": "Программирование",
        "keywords": ["программирование", "алгоритм", "язык программирования", "python", "java", "c++", "основы программирования"],
        "topics": [
            "Алгоритмы и способы их описания",
            "Переменные, типы данных и операции",
            "Условные операторы и циклы",
            "Функции, параметры и область видимости",
            "Массивы, списки и базовые структуры данных",
            "Строки и файловый ввод-вывод",
            "Основы отладки и тестирования программ",
            "Решение прикладных задач средствами программирования",
        ],
        "outcomes": [
            "Знать базовые конструкции языка программирования и принципы построения алгоритмов.",
            "Уметь разрабатывать простые программы для решения учебных и прикладных задач.",
            "Владеть навыками отладки, тестирования и анализа корректности программного кода.",
        ],
        "task_focus": "простые алгоритмические задачи, функции, циклы, массивы, отладка кода",
    },
    "web_development": {
        "label": "Разработка веб-приложений",
        "keywords": ["web", "веб", "html", "css", "javascript", "react", "vue", "frontend", "фронтенд", "веб-прилож"],
        "topics": [
            "Архитектура веб-приложений и клиент-серверное взаимодействие",
            "HTML-разметка и семантическая структура страницы",
            "CSS, адаптивная верстка и основы UI-композиции",
            "JavaScript: работа с DOM, событиями и асинхронностью",
            "HTTP, REST API и обмен данными с сервером",
            "Компонентный подход во frontend-разработке",
            "React/Vue: состояние, свойства, жизненный цикл и маршрутизация",
            "Тестирование, сборка и оптимизация веб-приложений",
        ],
        "outcomes": [
            "Знать принципы построения клиентской части веб-приложения и взаимодействия с API.",
            "Уметь разрабатывать интерфейсы с использованием HTML, CSS, JavaScript и компонентных фреймворков.",
            "Владеть навыками отладки, тестирования и оптимизации frontend-приложений.",
        ],
        "task_focus": "HTML/CSS/JS, компоненты React/Vue, работа с API, адаптивный интерфейс",
    },
    "computer_networks": {
        "label": "Компьютерные сети",
        "keywords": ["компьютерные сети", "телекоммуникации", "tcp", "ip", "маршрутизац", "сетев"],
        "topics": [
            "Основные понятия компьютерных сетей и модели взаимодействия",
            "Физический и канальный уровни передачи данных",
            "IP-адресация и подсети",
            "Маршрутизация и коммутация в сетях",
            "Транспортные протоколы TCP и UDP",
            "Прикладные сетевые протоколы и службы",
            "Основы сетевой безопасности",
            "Диагностика и настройка сетевых соединений",
        ],
        "outcomes": [
            "Знать принципы построения компьютерных сетей и назначение основных протоколов.",
            "Уметь выполнять базовую настройку и диагностику сетевого взаимодействия.",
            "Владеть навыками анализа сетевой конфигурации и выявления типовых ошибок.",
        ],
        "task_focus": "IP-адресация, протоколы, маршрутизация, диагностика сети",
    },
    "physics": {
        "label": "Физика",
        "keywords": ["физика", "механика", "электродинамика", "оптика", "термодинамика"],
        "topics": [
            "Кинематика и динамика материальной точки",
            "Законы сохранения в механике",
            "Молекулярная физика и термодинамика",
            "Электростатика и постоянный электрический ток",
            "Магнитное поле и электромагнитная индукция",
            "Колебания и волны",
            "Оптика и элементы квантовой физики",
            "Физический эксперимент и обработка результатов измерений",
        ],
        "outcomes": [
            "Знать основные физические законы, модели и области их применения.",
            "Уметь решать типовые физические задачи и интерпретировать результаты измерений.",
            "Владеть навыками применения физических закономерностей при анализе технических систем.",
        ],
        "task_focus": "расчетные задачи, законы физики, анализ эксперимента, единицы измерения",
    },
}

GENERIC_TOPIC_MARKERS = {
    "общие положения дисциплины",
    "основы дисциплины",
    "темы дисциплины",
    "наименование дисциплины",
}


def enrich_analysis_with_discipline_profile(filename: str, text: str, analysis: RpdAnalysisResult) -> RpdAnalysisResult:
    profile_key, confidence = detect_discipline_profile(filename, text, analysis.topics)
    if not profile_key or confidence < 1.0:
        return analysis

    profile = DOMAIN_PROFILES[profile_key]
    topics = _merge_topics(analysis.topics, profile["topics"])
    outcomes = _merge_topics(analysis.learning_outcomes, profile["outcomes"])
    warnings = list(analysis.diagnostics.warnings)

    should_enrich = _is_sparse_or_generic(analysis.topics)
    if not should_enrich:
        return analysis

    warnings.append(
        f"РПД содержит недостаточно предметных тем; применено доменное обогащение: {profile['label']}. "
        f"Фокус заданий: {profile['task_focus']}."
    )
    diagnostics = replace(
        analysis.diagnostics,
        topics_count=len(topics),
        learning_outcomes_count=len(outcomes),
        extraction_strategy=f"{analysis.diagnostics.extraction_strategy}+domain-profile:{profile_key}",
        warnings=warnings,
        quality_score=min(max(analysis.diagnostics.quality_score, 70), 100),
    )
    return replace(
        analysis,
        topics=topics,
        learning_outcomes=outcomes,
        topic_sources=list(analysis.topic_sources) + [f"Доменная база: {profile['label']}"],
        outcome_sources=list(analysis.outcome_sources) + [f"Доменная база: {profile['label']}"],
        diagnostics=diagnostics,
    )


def detect_discipline_profile(filename: str, text: str, topics: list[str] | None = None) -> tuple[str, float]:
    haystack = " ".join([filename or "", " ".join(topics or []), text[:5000] or ""]).lower().replace("ё", "е")
    best_key = ""
    best_score = 0.0
    for key, profile in DOMAIN_PROFILES.items():
        score = 0.0
        for keyword in profile["keywords"]:
            keyword_norm = keyword.lower().replace("ё", "е")
            if keyword_norm in haystack:
                score += 2.0 if len(keyword_norm) > 8 else 1.0
        if score > best_score:
            best_key = key
            best_score = score
    return best_key, best_score


def _is_sparse_or_generic(topics: list[str]) -> bool:
    if len(topics) < 4:
        return True
    generic_count = 0
    for topic in topics:
        normalized = topic.lower().strip().replace("ё", "е")
        if normalized in GENERIC_TOPIC_MARKERS:
            generic_count += 1
        if len(normalized.split()) <= 2:
            generic_count += 1
    return generic_count >= max(1, len(topics) // 2)


def _merge_topics(primary: list[str], fallback: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in [*primary, *fallback]:
        normalized = value.lower().strip().replace("ё", "е")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value.strip())
    return result[:40]
