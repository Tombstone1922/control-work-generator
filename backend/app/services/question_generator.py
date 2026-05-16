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
        "Выберите корректное утверждение по теме: {topic}.",
        "Какое из перечисленных положений относится к теме: {topic}?",
        "Определите верное описание ключевого понятия по теме: {topic}.",
        "Укажите вариант, который наиболее точно раскрывает содержание темы: {topic}.",
    ],
    "practice": [
        "Решите практическую задачу, связанную с темой: {topic}.",
        "Приведите пример применения темы: {topic} в учебной или профессиональной ситуации.",
        "Разберите прикладную ситуацию, в которой используется тема: {topic}.",
        "Составьте краткий алгоритм решения задачи по теме: {topic}.",
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
    )


def _adapt_by_difficulty(text: str, difficulty: str) -> str:
    difficulty = difficulty.lower().strip()
    if difficulty == "easy":
        return f"Дайте краткий ответ. {text}"
    if difficulty == "hard":
        return f"Дайте развернутый ответ с обоснованием и примером. {text}"
    return text
