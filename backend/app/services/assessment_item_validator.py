import re
from collections import defaultdict
from difflib import SequenceMatcher

from app.assessment_item_validation import (
    AssessmentCoverageRow,
    AssessmentDuplicateGroup,
    AssessmentItemsValidation,
)
from app.schemas import AssessmentItemRead
from app.services.assessment_item_smart_builder import normalize_topic

PLACEHOLDER_MARKERS = (
    "формируется и уточняется преподавателем",
    "необходимо уточнить преподавателю",
)


def validate_assessment_items(
    items: list[AssessmentItemRead],
    topics: list[str],
    competency_codes: list[str],
) -> AssessmentItemsValidation:
    normalized_topics = [normalize_topic(topic) for topic in topics if topic.strip()]
    normalized_topics = list(dict.fromkeys(topic for topic in normalized_topics if topic))
    normalized_competencies = [code.strip() for code in competency_codes if code.strip()]

    empty_answer_item_ids = [item.id for item in items if not item.answer.strip()]
    placeholder_answer_item_ids = [
        item.id
        for item in items
        if item.answer.strip() and any(marker in item.answer.lower() for marker in PLACEHOLDER_MARKERS)
    ]
    empty_criteria_item_ids = [item.id for item in items if not [value for value in item.criteria if value.strip()]]
    missing_topic_item_ids = [item.id for item in items if not item.topic.strip()]
    missing_competency_item_ids = [item.id for item in items if not item.competency_code.strip()]

    covered_topics = {normalize_topic(item.topic) for item in items if item.topic.strip()}
    covered_competencies = {item.competency_code.strip() for item in items if item.competency_code.strip()}
    duplicate_groups = _find_duplicate_groups(items)
    duplicate_ids = {item_id for group in duplicate_groups for item_id in group.item_ids}

    coverage_rows = _build_coverage_rows(normalized_topics, items)
    topics_score = round(100 * len(covered_topics.intersection(normalized_topics)) / max(len(normalized_topics), 1))
    competencies_score = round(
        100 * len(covered_competencies.intersection(normalized_competencies)) / max(len(normalized_competencies), 1)
    ) if normalized_competencies else 0
    answers_ready = len(items) - len(set(empty_answer_item_ids + placeholder_answer_item_ids))
    answers_score = round(100 * answers_ready / max(len(items), 1))
    criteria_score = round(100 * (len(items) - len(empty_criteria_item_ids)) / max(len(items), 1))
    duplicate_rate = round(100 * len(duplicate_ids) / max(len(items), 1), 2)

    warnings: list[str] = []
    if not items:
        warnings.append("Банк заданий пока пуст.")
    if topics_score < 100:
        warnings.append("Не все темы дисциплины покрыты заданиями.")
    if normalized_competencies and competencies_score < 100:
        warnings.append("Не все компетенции покрыты заданиями.")
    if empty_answer_item_ids:
        warnings.append("У части заданий отсутствуют эталонные ответы.")
    if placeholder_answer_item_ids:
        warnings.append("В банке остаются шаблонные ответы, требующие экспертного уточнения.")
    if empty_criteria_item_ids:
        warnings.append("У части заданий отсутствуют критерии оценивания.")
    if missing_topic_item_ids:
        warnings.append("У части заданий не указана тема.")
    if missing_competency_item_ids:
        warnings.append("У части заданий не указана компетенция.")
    if duplicate_groups:
        warnings.append("Обнаружены потенциальные дубли формулировок заданий.")

    return AssessmentItemsValidation(
        total_items=len(items),
        topics_total=len(normalized_topics),
        topics_covered=len(covered_topics.intersection(normalized_topics)),
        competencies_total=len(normalized_competencies),
        competencies_covered=len(covered_competencies.intersection(normalized_competencies)),
        topics_coverage_score=topics_score,
        competencies_coverage_score=competencies_score,
        answers_readiness_score=answers_score,
        criteria_readiness_score=criteria_score,
        duplicate_rate=duplicate_rate,
        empty_answer_item_ids=empty_answer_item_ids,
        placeholder_answer_item_ids=placeholder_answer_item_ids,
        empty_criteria_item_ids=empty_criteria_item_ids,
        missing_topic_item_ids=missing_topic_item_ids,
        missing_competency_item_ids=missing_competency_item_ids,
        duplicate_groups=duplicate_groups,
        coverage_rows=coverage_rows,
        warnings=warnings,
    )


def _build_coverage_rows(topics: list[str], items: list[AssessmentItemRead]) -> list[AssessmentCoverageRow]:
    rows: list[AssessmentCoverageRow] = []
    for topic in topics:
        topic_items = [item for item in items if normalize_topic(item.topic) == topic]
        section_counts: dict[str, int] = defaultdict(int)
        competencies: set[str] = set()
        for item in topic_items:
            section_counts[item.section_code] += 1
            if item.competency_code.strip():
                competencies.add(item.competency_code.strip())
        rows.append(
            AssessmentCoverageRow(
                topic=topic,
                total_items=len(topic_items),
                section_counts=dict(section_counts),
                competencies=sorted(competencies),
            )
        )
    return rows


def _find_duplicate_groups(items: list[AssessmentItemRead]) -> list[AssessmentDuplicateGroup]:
    groups: list[AssessmentDuplicateGroup] = []
    used_pairs: set[tuple[str, str]] = set()
    for index, first in enumerate(items):
        first_text = _normalize_text(first.text)
        if not first_text:
            continue
        current_ids = [first.id]
        best_similarity = 0.0
        for second in items[index + 1:]:
            if first.section_code != second.section_code:
                continue
            second_text = _normalize_text(second.text)
            if not second_text:
                continue
            pair = tuple(sorted((first.id, second.id)))
            if pair in used_pairs:
                continue
            similarity = SequenceMatcher(None, first_text, second_text).ratio()
            if similarity >= 0.92:
                current_ids.append(second.id)
                best_similarity = max(best_similarity, similarity)
                used_pairs.add(pair)
        if len(current_ids) > 1:
            groups.append(
                AssessmentDuplicateGroup(
                    item_ids=current_ids,
                    sample_text=first.text,
                    similarity=round(best_similarity, 3),
                )
            )
    return groups


def _normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[«»\"'.,:;!?()\[\]{}]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value
