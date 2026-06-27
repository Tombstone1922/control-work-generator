from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models
from app.repositories_assessment_items import get_fund_entity_for_user, replace_items_for_sections
from app.repositories_reference_materials import list_om_generation_examples_for_fund, training_example_to_weighted
from app.repositories_training_examples import list_training_examples_for_user
from app.schemas import (
    AssessmentCompetencyRead,
    AssessmentFundSection,
    AssessmentItemRead,
    AssessmentItemsGenerateRequest,
    AssessmentItemsGenerateResponse,
)
from app.services.assessment_fund_builder import validate_assessment_fund
from app.services.assessment_item_generator import ItemGenerationContext, generate_items_for_section
from app.services.assessment_item_postprocessor import postprocess_generated_items
from app.services.local_llm_client import LocalLLMClient, get_local_llm_settings
from app.services.narrow_llm_service import apply_narrow_llm_generation
from app.services.reference_library import find_om_examples_for_program, get_reference_library_path
from app.services.role_policy import ensure_can_edit_fund_content

INTELLIGENT_V2_MODE = "intelligent_v2"
INTELLIGENT_V2_MODEL_VERSION = "intelligent-fos-generator-v2.1-fast"

# Базовый профиль составлен по реальному ОМ:
# 40 устных вопросов, 20 практических текущего контроля,
# 32 вопроса к зачету, 13 практических заданий к зачету,
# 40 заданий итоговой диагностической работы.
OM_V2_SECTION_PLAN: list[tuple[str, str, str, int]] = [
    ("current_oral", "2.1 Вопросы для устного опроса", "oral", 40),
    ("current_practice", "2.1 Практические задания для текущего контроля", "practice", 20),
    ("intermediate_credit", "2.2 Вопросы к зачету", "credit", 32),
    ("intermediate_credit_practice", "2.2 Практические задания для проведения зачета", "credit_practice", 13),
    ("diagnostic", "2.3 Итоговая диагностическая работа по дисциплине", "diagnostic", 40),
]
OM_V2_TOTAL_ITEMS = sum(item[3] for item in OM_V2_SECTION_PLAN)
V2_LLM_TARGET_LIMIT = 40
# Было 5 => 8 запросов для 40 заданий. Теперь 8 => 5 запросов, JSON остается коротким,
# потому что модель возвращает только text без answer/criteria.
V2_LLM_BATCH_SIZE = 8
V2_TEXT_MAX_CHARS = 520

TEXT_ONLY_SYSTEM_PROMPT = """
/no_think
Ты методист вуза. Быстро улучши формулировки оценочных материалов.
Не меняй тип задания. Не рассуждай. Не используй markdown в ответе.
Верни только JSON: {"items":[{"index":0,"text":"..."}]}.
Только поля index и text. Без answer, criteria и пояснений.
""".strip()


@dataclass
class TextOnlyLLMProfile:
    enabled: bool
    profile: str
    model: str
    base_url: str
    requested_items: int
    refined_items: int = 0
    failed_items: int = 0
    calls: int = 0
    llm_ms: int = 0
    avg_call_ms: int = 0
    call_ms: list[int] | None = None

    def as_dict(self) -> dict:
        call_ms = self.call_ms or []
        return {
            "enabled": self.enabled,
            "profile": self.profile,
            "model": self.model,
            "base_url": self.base_url,
            "requested_items": self.requested_items,
            "refined_items": self.refined_items,
            "failed_items": self.failed_items,
            "calls": self.calls,
            "llm_ms": self.llm_ms,
            "avg_call_ms": self.avg_call_ms,
            "call_ms": call_ms[:12],
            "mode": "intelligent-v2-text-only-fast",
            "batch_size": V2_LLM_BATCH_SIZE,
        }


def generate_intelligent_v2_bank(
    *,
    db: Session,
    fund_id: str,
    payload: AssessmentItemsGenerateRequest,
    current_user: models.User,
) -> AssessmentItemsGenerateResponse | None:
    total_started = time.perf_counter()
    profiling: dict = {
        "stages_ms": {},
        "sections_total": 0,
        "topics_total": 0,
        "items_before_llm": 0,
        "items_after_llm": 0,
        "items_persisted": 0,
        "intelligent_v2_plan": {
            "target_total": OM_V2_TOTAL_ITEMS,
            "llm_target_limit": V2_LLM_TARGET_LIMIT,
            "sections": [
                {"code": code, "title": title, "assessment_type": assessment_type, "planned_items": planned}
                for code, title, assessment_type, planned in OM_V2_SECTION_PLAN
            ],
        },
    }

    stage_started = time.perf_counter()
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        return None
    ensure_can_edit_fund_content(current_user, fund)
    profiling["stages_ms"]["load_fund"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    topics = _load_topics(fund)
    competencies = _competencies(fund)
    all_sections = _standardize_sections_for_v2(fund, topics, competencies)
    selected_sections = _selected_sections_for_v2(all_sections, payload.section_code)
    if payload.section_code and not selected_sections:
        raise ValueError("Раздел ФОС не найден.")
    profiling["sections_total"] = len(selected_sections)
    profiling["topics_total"] = len(topics)
    profiling["competencies_total"] = len(competencies)
    profiling["stages_ms"]["prepare_context"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    generated: list[AssessmentItemRead] = []
    target_codes: list[str] = []
    used_texts: list[str] = []
    max_plan = max((section.planned_items for section in selected_sections), default=payload.max_items_per_section)
    for section in selected_sections:
        target_codes.append(section.code)
        generated.extend(
            generate_items_for_section(
                ItemGenerationContext(
                    fund_id=fund.id,
                    section=section,
                    topics=topics,
                    competencies=competencies,
                    max_items=max(max_plan, payload.max_items_per_section),
                    discipline_name=fund.discipline_name,
                    used_texts=used_texts,
                )
            )
        )
    profiling["items_before_llm"] = len(generated)
    profiling["stages_ms"]["context_generator"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    expert_examples = [training_example_to_weighted(item) for item in list_training_examples_for_user(db, current_user)]
    uploaded_om_examples = list_om_generation_examples_for_fund(db, current_user, fund)
    om_match = find_om_examples_for_program(
        program_filename=fund.program.filename,
        program_text=fund.program.text_preview,
        fund_id=fund.id,
        discipline_name=fund.discipline_name,
        topics=topics,
    )
    generation_examples = uploaded_om_examples + om_match.examples + expert_examples
    profiling["examples"] = {
        "expert": len(expert_examples),
        "uploaded_om": len(uploaded_om_examples),
        "folder_om": len(om_match.examples),
        "total": len(generation_examples),
    }
    profiling["stages_ms"]["load_examples"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    generation_result = apply_narrow_llm_generation(
        items=generated,
        training_examples=generation_examples,
        requested_mode="hybrid",
        narrow_max_items=payload.narrow_max_items,
        fallback_to_template=True,
    )
    profiling["stages_ms"]["narrow_or_example_generation"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    preclean_items, preclean_warnings = postprocess_generated_items(
        generation_result.items,
        discipline_name=fund.discipline_name,
        all_topics=topics,
    )
    profiling["stages_ms"]["pre_postprocess"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    llm_targets = _select_llm_targets(preclean_items, limit=V2_LLM_TARGET_LIMIT)
    refined_targets, llm_warnings, local_llm_profile = _refine_text_only_targets(
        items=llm_targets,
        discipline_name=fund.discipline_name,
        all_topics=topics,
    )
    profiling["local_llm"] = local_llm_profile
    profiling["intelligent_v2_llm_targets"] = {
        "selected": len(llm_targets),
        "limit": V2_LLM_TARGET_LIMIT,
        "types": _count_by_type(llm_targets),
    }
    merged_items = _merge_refined_items(preclean_items, refined_targets)
    profiling["stages_ms"]["local_llm_refinement"] = _elapsed_ms(stage_started)
    profiling["items_after_llm"] = len(merged_items)

    stage_started = time.perf_counter()
    cleaned_items, cleanup_warnings = postprocess_generated_items(
        merged_items,
        discipline_name=fund.discipline_name,
        all_topics=topics,
    )
    profiling["stages_ms"]["final_postprocess"] = _elapsed_ms(stage_started)

    warnings = [
        f"Интеллектуальный генератор 2.0 сформировал OM/ФОС-профиль на {len(cleaned_items)} элементов: 40 устных вопросов, 20 практических заданий текущего контроля, 32 вопроса к зачету, 13 практических заданий к зачету и 40 диагностических заданий.",
        f"Локальная 14B-модель дорабатывала только сложные элементы: выбрано {len(llm_targets)} из {len(preclean_items)}.",
    ]
    warnings += list(om_match.warnings) + list(generation_result.warnings) + preclean_warnings + llm_warnings + cleanup_warnings
    if uploaded_om_examples:
        warnings.insert(1, f"База загруженных OM добавила эталонных заданий: {len(uploaded_om_examples)}.")
    if om_match.examples:
        warnings.append(f"Папочная база OM добавила примеров: {len(om_match.examples)}. Папка: {get_reference_library_path()}")

    stage_started = time.perf_counter()
    persisted = replace_items_for_sections(
        db,
        fund,
        target_codes,
        cleaned_items,
        payload.replace_existing,
    )
    profiling["stages_ms"]["persist_items"] = _elapsed_ms(stage_started)
    profiling["items_persisted"] = len([item for item in persisted if item.section_code in set(target_codes)])
    profiling["total_ms"] = _elapsed_ms(total_started)

    return AssessmentItemsGenerateResponse(
        items=persisted,
        requested_mode=payload.generation_mode,
        used_mode=INTELLIGENT_V2_MODE,
        learned_generated_items=generation_result.learned_generated_items,
        narrow_llm_generated_items=getattr(generation_result, "narrow_llm_generated_items", 0),
        template_generated_items=max(0, len(cleaned_items) - getattr(generation_result, "narrow_llm_generated_items", 0)),
        model_version=INTELLIGENT_V2_MODEL_VERSION,
        warnings=warnings,
        profiling=profiling,
    )


def _standardize_sections_for_v2(
    fund: models.AssessmentFund,
    topics: list[str],
    competencies: list[AssessmentCompetencyRead],
) -> list[AssessmentFundSection]:
    raw_sections = json.loads(fund.sections_json or "[]")
    sections = [AssessmentFundSection(**raw) for raw in raw_sections]
    by_code = {section.code: section for section in sections}

    for code, title, assessment_type, planned in OM_V2_SECTION_PLAN:
        if code in by_code:
            section = by_code[code]
            section.title = title
            section.description = _section_description(assessment_type, planned)
            section.assessment_type = assessment_type
            section.enabled = True
            section.topics = topics
            section.planned_items = planned
        else:
            section = AssessmentFundSection(
                code=code,
                title=title,
                description=_section_description(assessment_type, planned),
                assessment_type=assessment_type,
                enabled=True,
                topics=topics,
                planned_items=planned,
                generated_items=0,
            )
            sections.append(section)
            by_code[code] = section

    target_types = {assessment_type for _, _, assessment_type, _ in OM_V2_SECTION_PLAN}
    assessment_types = list(dict.fromkeys(json.loads(fund.assessment_types_json or "[]") + list(target_types)))
    validation = validate_assessment_fund(sections, competencies, topics)
    fund.sections_json = json.dumps([section.model_dump() for section in sections], ensure_ascii=False)
    fund.assessment_types_json = json.dumps(assessment_types, ensure_ascii=False)
    fund.validation_json = json.dumps(validation.model_dump(), ensure_ascii=False)
    return sections


def _selected_sections_for_v2(sections: list[AssessmentFundSection], section_code: str | None) -> list[AssessmentFundSection]:
    target_codes = {code for code, _, _, _ in OM_V2_SECTION_PLAN}
    result = []
    for section in sections:
        if section_code and section.code != section_code:
            continue
        if not section_code and section.code not in target_codes:
            continue
        if not section.enabled:
            continue
        result.append(section)
    return result


def _refine_text_only_targets(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
) -> tuple[list[AssessmentItemRead], list[str], dict]:
    settings = get_local_llm_settings(None)
    profile = TextOnlyLLMProfile(
        enabled=settings.enabled,
        profile=settings.profile,
        model=settings.model,
        base_url=settings.base_url,
        requested_items=len(items),
        call_ms=[],
    )
    if not items:
        return [], [], profile.as_dict()
    if not settings.enabled:
        return items, ["Локальная 14B-модель отключена; сложные элементы оставлены после context-builder и narrow-generator."], profile.as_dict()

    client = LocalLLMClient(settings)
    result: list[AssessmentItemRead] = []
    warnings: list[str] = []
    for batch_start in range(0, len(items), V2_LLM_BATCH_SIZE):
        batch = items[batch_start: batch_start + V2_LLM_BATCH_SIZE]
        prompt = _build_text_only_prompt(
            batch=batch,
            batch_start=batch_start,
            discipline_name=discipline_name,
            all_topics=all_topics,
        )
        call_started = time.perf_counter()
        data = client.chat_json(system_prompt=TEXT_ONLY_SYSTEM_PROMPT, user_prompt=prompt)
        call_ms = _elapsed_ms(call_started)
        profile.calls += 1
        profile.llm_ms += call_ms
        profile.call_ms.append(call_ms)

        candidates = _extract_text_candidates(data or {})
        by_index = {candidate["index"]: candidate["text"] for candidate in candidates}
        for local_index, item in enumerate(batch):
            candidate_text = by_index.get(batch_start + local_index) or by_index.get(local_index)
            if not candidate_text:
                result.append(item)
                profile.failed_items += 1
                continue
            text = _repair_text_for_type(candidate_text, item)
            if not _is_usable_text(text, item):
                result.append(item)
                profile.failed_items += 1
                continue
            result.append(
                item.model_copy(update={
                    "text": text,
                    "source_kind": "local_llm_qwen3_v2",
                    "source_context": f"Intelligent generator 2.0 fast text-only 14B refinement; profile={settings.profile}; model={settings.model}; batch_size={V2_LLM_BATCH_SIZE}.",
                })
            )
            profile.refined_items += 1

    profile.avg_call_ms = int(profile.llm_ms / profile.calls) if profile.calls else 0
    if profile.refined_items:
        warnings.append(f"Интеллектуальный генератор 2.0: 14B-модель улучшила сложные элементы: {profile.refined_items}; запросов: {profile.calls}.")
    if profile.failed_items:
        warnings.append(f"Интеллектуальный генератор 2.0: 14B-модель не вернула пригодную формулировку для элементов: {profile.failed_items}; оставлены базовые формулировки.")
    return result, warnings, profile.as_dict()


def _build_text_only_prompt(
    *,
    batch: list[AssessmentItemRead],
    batch_start: int,
    discipline_name: str,
    all_topics: list[str],
) -> str:
    # Не markdown: компактный line/TSV-подобный формат короче JSON-входа и быстрее для локальной модели.
    lines = [
        f"Дисциплина: {_compact(discipline_name, 90)}",
        "Задача: улучшить только формулировку text. Вернуть JSON: {\"items\":[{\"index\":0,\"text\":\"...\"}]}",
        f"Ограничение: text <= {V2_TEXT_MAX_CHARS} символов; один результат на каждый index; без markdown и пояснений.",
        "Данные: index|type|topic|level|competency|contract|current_text",
    ]
    for index, item in enumerate(batch):
        lines.append(
            "|".join([
                str(batch_start + index),
                _compact(item.assessment_type, 32),
                _compact(item.topic, 90),
                _compact(item.difficulty, 16),
                _compact(item.competency_code, 32),
                _compact(_type_contract(item.assessment_type), 120),
                _compact(item.text, 210),
            ])
        )
    return "\n".join(lines)


def _extract_text_candidates(data: dict) -> list[dict]:
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        raw_items = [data]
    result = []
    for fallback_index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        text = _clean_text(raw.get("text"))
        if not text:
            continue
        try:
            index = int(raw.get("index", fallback_index))
        except (TypeError, ValueError):
            index = fallback_index
        result.append({"index": index, "text": text})
    return result


def _select_llm_targets(items: list[AssessmentItemRead], *, limit: int) -> list[AssessmentItemRead]:
    practical_types = {"practice", "credit_practice", "exam_practice", "control_work", "laboratory"}
    diagnostic_types = {"diagnostic"}
    result: list[AssessmentItemRead] = []
    for item in items:
        if item.assessment_type in practical_types:
            result.append(item)
            if len(result) >= limit:
                return result
    for item in items:
        if item.assessment_type in diagnostic_types:
            result.append(item)
            if len(result) >= limit:
                return result
    return result[:limit]


def _merge_refined_items(items: list[AssessmentItemRead], refined: list[AssessmentItemRead]) -> list[AssessmentItemRead]:
    by_id = {item.id: item for item in refined}
    return [by_id.get(item.id, item) for item in items]


def _competencies(fund: models.AssessmentFund) -> list[AssessmentCompetencyRead]:
    return [
        AssessmentCompetencyRead(
            id=item.id,
            code=item.code,
            description=item.description,
            indicators=json.loads(item.indicators_json or "[]"),
            levels=json.loads(item.levels_json or "[]"),
        )
        for item in fund.competencies
    ]


def _load_topics(fund: models.AssessmentFund) -> list[str]:
    topics = json.loads(fund.program.topics_json or "[]")
    return [str(topic).strip() for topic in topics if str(topic).strip()] or ["Общие положения дисциплины"]


def _section_description(assessment_type: str, planned: int) -> str:
    labels = {
        "oral": "устные вопросы текущего контроля",
        "practice": "практические задания текущего контроля",
        "credit": "теоретические вопросы к зачету",
        "credit_practice": "практические задания к зачету",
        "diagnostic": "итоговая диагностическая работа",
    }
    label = labels.get(assessment_type, assessment_type)
    return f"Интеллектуальный генератор 2.0: {label}, плановое количество — {planned}."


def _type_contract(assessment_type: str) -> str:
    if assessment_type in {"practice", "credit_practice", "exam_practice", "control_work", "laboratory"}:
        return "Начни с 'Практическое задание:' и требуй проверяемый результат."
    if assessment_type == "diagnostic":
        return "Начни с 'Диагностическое задание:' или сформулируй тестовую/кейсовую проверку."
    return "Начни с 'Вопрос:' и не делай практическую работу."


def _repair_text_for_type(text: str, item: AssessmentItemRead) -> str:
    text = _clean_text(text)
    lower = text.lower()
    if item.assessment_type in {"practice", "credit_practice", "exam_practice", "control_work", "laboratory"} and not lower.startswith("практическое задание"):
        return f"Практическое задание: {text}"
    if item.assessment_type == "diagnostic" and not lower.startswith("диагностическое задание"):
        return f"Диагностическое задание: {text}"
    if item.assessment_type in {"oral", "exam_questions", "credit"} and not lower.startswith("вопрос"):
        return f"Вопрос: {text[:1].lower()}{text[1:]}" if text else text
    return text


def _is_usable_text(text: str, item: AssessmentItemRead) -> bool:
    text = _clean_text(text)
    lower = text.lower()
    if not 25 <= len(text) <= 800:
        return False
    if any(marker in lower for marker in ("я не могу", "как языковая модель", "markdown", "json")):
        return False
    if item.assessment_type in {"practice", "credit_practice", "exam_practice", "control_work", "laboratory"}:
        return lower.startswith("практическое задание") or any(word in lower[:160] for word in ("разработайте", "выполните", "создайте", "реализуйте", "составьте"))
    if item.assessment_type == "diagnostic":
        return lower.startswith("диагностическое задание") or "?" in text[:260] or "выберите" in lower[:180]
    return True


def _count_by_type(items: list[AssessmentItemRead]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.assessment_type] = counts.get(item.assessment_type, 0) + 1
    return counts


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" .;:-—\t\n\r")


def _compact(value: str, limit: int) -> str:
    value = _clean_text(value).replace("|", "/")
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


def _trim(value: str, limit: int) -> str:
    value = _clean_text(value)
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
