from app.schemas import ControlWorkVariant, QualityReport


def build_quality_report(variants: list[ControlWorkVariant], source_topics: list[str]) -> QualityReport:
    all_questions = [question for variant in variants for question in variant.questions]
    generated_topics = {question.topic.lower() for question in all_questions}
    source_topic_keys = {topic.lower() for topic in source_topics}

    if source_topic_keys:
        topic_coverage = len(generated_topics.intersection(source_topic_keys)) / len(source_topic_keys)
    else:
        topic_coverage = 1.0

    texts = [question.text.lower().strip() for question in all_questions]
    duplicate_count = len(texts) - len(set(texts))
    duplicate_rate = duplicate_count / len(texts) if texts else 0.0

    recommendations: list[str] = []
    if topic_coverage < 0.8:
        recommendations.append("Рекомендуется увеличить количество заданий или включить недостающие темы РПД.")
    if duplicate_rate > 0.1:
        recommendations.append("Обнаружены похожие задания. Рекомендуется выполнить повторную генерацию части вопросов.")
    if not recommendations:
        recommendations.append("Критических замечаний не обнаружено. Результат может быть передан на экспертную проверку.")

    return QualityReport(
        topic_coverage=round(topic_coverage, 3),
        duplicate_rate=round(duplicate_rate, 3),
        total_questions=len(all_questions),
        recommendations=recommendations,
    )
