from uuid import uuid4

from app.schemas import ControlWorkVariant, Question


QUESTION_TEMPLATES = {
    "open": [
        "Раскройте сущность темы: {topic}.",
        "Объясните основные понятия и принципы, связанные с темой: {topic}.",
        "Опишите практическое значение темы: {topic}.",
        "Сформулируйте основные положения темы: {topic} и приведите пример.",
        "Проанализируйте значение темы: {topic} для освоения дисциплины.",
    ],
    "test": [
        "Какое утверждение наиболее точно раскрывает тему «{topic}»?",
        "Что является корректным описанием темы «{topic}»?",
        "Какой вариант лучше всего соответствует содержанию темы «{topic}»?",
        "Выберите верное утверждение по теме «{topic}».",
    ],
    "practice": [
        "Решите практическую задачу, связанную с темой: {topic}.",
        "Приведите пример применения темы: {topic} в учебной или профессиональной ситуации.",
        "Разберите прикладную ситуацию, в которой используется тема: {topic}.",
        "Составьте краткий алгоритм решения задачи по теме: {topic}.",
    ],
}


TEST_OPTIONS = (
    "A. Тема описывает принцип, который помогает правильно спроектировать, реализовать или проверить элемент веб-приложения",
    "B. Тема сводится только к изменению цвета и внешнего вида без влияния на структуру решения",
    "C. Тема не связана с разработкой программного обеспечения и не применяется при создании веб-приложений",
    "D. Тема означает удаление исходных данных без обработки и проверки результата",
)


CRITERIA_BY_TYPE = {
    "open": [
        "Дано корректное определение или объяснение темы.",
        "Указано практическое назначение темы в разработке веб-приложений.",
        "Приведен пример применения или проверки результата.",
    ],
    "test": [
        "Выбран вариант A.",
        "Дано краткое обоснование выбора.",
        "Ответ связан с темой задания.",
    ],
    "practice": [
        "Предложенное решение связано с темой задания.",
        "Указаны основные шаги реализации или применения.",
        "Описан ожидаемый результат и способ проверки.",
    ],
}


def generate_variants(
    topics: list[str],
    variants_count: int,
    questions_per_variant: int,
    difficulty: str,
    question_types: list[str],
) -> list[ControlWorkVariant]:
    safe_topics = topics or ["Общие положения дисциплины"]
    safe_types = question_types or ["open"]
    variants: list[ControlWorkVariant] = []

    for variant_number in range(1, variants_count + 1):
        questions: list[Question] = []
        for index in range(questions_per_variant):
            topic = safe_topics[(index + variant_number - 1) % len(safe_topics)]
            question_type = safe_types[index % len(safe_types)]
            questions.append(
                generate_question(
                    topic=topic,
                    question_type=question_type,
                    difficulty=difficulty,
                    seed=index + variant_number - 1,
                )
            )

        variants.append(ControlWorkVariant(variant_number=variant_number, questions=questions))

    return variants


def generate_question(
    topic: str,
    question_type: str,
    difficulty: str,
    seed: int = 0,
    avoid_texts: list[str] | None = None,
) -> Question:
    templates = QUESTION_TEMPLATES.get(question_type, QUESTION_TEMPLATES["open"])
    avoid = {text.lower().strip() for text in (avoid_texts or [])}

    selected_text = ""
    for offset in range(len(templates)):
        template = templates[(seed + offset) % len(templates)]
        candidate = _adapt_by_difficulty(template.format(topic=topic), difficulty)
        if question_type == "test":
            candidate = f"{candidate}\n" + "\n".join(TEST_OPTIONS)
        if candidate.lower().strip() not in avoid:
            selected_text = candidate
            break

    if not selected_text:
        selected_text = _adapt_by_difficulty(
            f"Сформулируйте развернутый ответ по теме: {topic}.",
            difficulty,
        )

    return Question(
        id=str(uuid4()),
        topic=topic,
        text=selected_text,
        type=question_type,
        difficulty=difficulty,
        answer=_build_answer(topic, question_type),
        criteria=CRITERIA_BY_TYPE.get(question_type, CRITERIA_BY_TYPE["open"]),
    )


def _adapt_by_difficulty(text: str, difficulty: str) -> str:
    difficulty = difficulty.lower().strip()
    if difficulty == "easy":
        return f"Дайте краткий ответ. {text}"
    if difficulty == "hard":
        return f"Дайте развернутый ответ с обоснованием и примером. {text}"
    return text


def _build_answer(topic: str, question_type: str) -> str:
    topic_l = topic.lower()
    core = _topic_core(topic, topic_l)
    if question_type == "test":
        return f"Правильный ответ: A. {core} Остальные варианты неверны, потому что сужают тему до внешнего оформления, отрывают ее от разработки или описывают некорректную обработку данных."
    if question_type == "practice":
        return (
            f"Решение: для темы «{topic}» нужно выделить цель применения, входные данные, последовательность действий и проверяемый результат. "
            f"{core} Практический ответ должен показывать, как этот принцип применяется в веб-приложении: какие элементы создаются, как они взаимодействуют, какие ошибки учитываются и по каким признакам проверяется корректность результата."
        )
    return f"{core} В ответе также нужно указать, где это применяется в веб-приложении, какие данные или элементы участвуют в процессе и как можно проверить, что решение работает корректно."


def _topic_core(topic: str, topic_l: str) -> str:
    if "html" in topic_l or "размет" in topic_l or "семантичес" in topic_l:
        return "HTML задает смысловую структуру страницы: заголовки, разделы, формы, списки, ссылки и основные блоки интерфейса. Семантическая разметка помогает браузеру, поисковым системам и средствам доступности правильно понимать назначение элементов."
    if "css" in topic_l or "адаптив" in topic_l or "ui" in topic_l:
        return "CSS отвечает за визуальное оформление и адаптивность интерфейса: сетки, отступы, размеры, состояния элементов и корректное отображение на разных экранах. Хорошая UI-композиция делает интерфейс понятным, единообразным и удобным для пользователя."
    if "javascript" in topic_l or "dom" in topic_l or "асинхрон" in topic_l:
        return "JavaScript управляет поведением страницы: обрабатывает события пользователя, изменяет DOM, выполняет валидацию, отправляет асинхронные запросы и обновляет интерфейс без перезагрузки страницы."
    if "http" in topic_l or "rest" in topic_l or "api" in topic_l or "сервер" in topic_l:
        return "HTTP и REST API обеспечивают обмен данными между клиентом и сервером. Клиент отправляет запросы, сервер возвращает ответ со статусом и данными, а приложение обрабатывает успешные и ошибочные сценарии."
    if "react" in topic_l or "состоя" in topic_l or "компонент" in topic_l:
        return "React позволяет строить интерфейс из компонентов, хранить состояние, передавать данные через свойства и обновлять отображение при изменении данных. Такой подход упрощает поддержку и повторное использование частей интерфейса."
    if "тест" in topic_l or "сборк" in topic_l or "оптимиза" in topic_l:
        return "Тестирование, сборка и оптимизация нужны для проверки корректности приложения, подготовки production-версии, уменьшения размера ресурсов и повышения скорости загрузки веб-интерфейса."
    if "архитект" in topic_l or "клиент" in topic_l:
        return "Архитектура веб-приложения определяет разделение ответственности между клиентской частью, сервером, API, базой данных и внешними сервисами. Это помогает сделать систему расширяемой и понятной для сопровождения."
    if "frontend" in topic_l or "фронтенд" in topic_l:
        return "Frontend-разработка отвечает за клиентскую часть приложения: интерфейс, взаимодействие пользователя с системой, обработку событий, отображение данных и связь с серверным API."
    return f"Тема «{topic}» описывает важный элемент разработки программного обеспечения: его назначение, правила применения, связь с другими частями системы и влияние на качество итогового веб-приложения."
