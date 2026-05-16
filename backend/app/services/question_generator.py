from uuid import uuid4

from app.schemas import ControlWorkVariant, Question


QUESTION_TEMPLATES = {
    "open": [
        "Раскройте сущность темы: {topic}.",
        "Объясните основные понятия и принципы, связанные с темой: {topic}.",
        "Опишите практическое значение темы: {topic}.",
    ],
    "test": [
        "Выберите корректное утверждение по теме: {topic}.",
        "Какое из перечисленных положений относится к теме: {topic}?",
    ],
    "practice": [
        "Решите практическую задачу, связанную с темой: {topic}.",
        "Приведите пример применения темы: {topic} в учебной или профессиональной ситуации.",
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
            templates = QUESTION_TEMPLATES.get(question_type, QUESTION_TEMPLATES["open"])
            template = templates[(index + variant_number - 1) % len(templates)]

            questions.append(
                Question(
                    id=str(uuid4()),
                    topic=topic,
                    text=_adapt_by_difficulty(template.format(topic=topic), difficulty),
                    type=question_type,
                    difficulty=difficulty,
                )
            )

        variants.append(ControlWorkVariant(variant_number=variant_number, questions=questions))

    return variants


def _adapt_by_difficulty(text: str, difficulty: str) -> str:
    difficulty = difficulty.lower().strip()
    if difficulty == "easy":
        return f"Дайте краткий ответ. {text}"
    if difficulty == "hard":
        return f"Дайте развернутый ответ с обоснованием и примером. {text}"
    return text
