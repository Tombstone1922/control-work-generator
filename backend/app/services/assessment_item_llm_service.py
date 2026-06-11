from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import AssessmentItemRead
from app.services.ollama_client import OllamaClientError, generate_assessment_item, resolve_ollama_model


@dataclass
class LocalGenerationResult:
    items: list[AssessmentItemRead]
    used_mode: str
    ollama_model: str = ""
    ollama_generated_items: int = 0
    template_generated_items: int = 0
    warnings: list[str] = field(default_factory=list)


def apply_local_llm_generation(
    *,
    items: list[AssessmentItemRead],
    requested_mode: str,
    discipline_name: str,
    source_text: str,
    requested_model: str | None,
    ollama_max_items: int,
    fallback_to_template: bool,
) -> LocalGenerationResult:
    mode = requested_mode.strip().lower()
    if mode not in {"template", "hybrid", "ollama"}:
        raise ValueError("Недопустимый режим генерации. Используйте template, hybrid или ollama.")

    if mode == "template" or not items:
        return LocalGenerationResult(
            items=items,
            used_mode="template",
            template_generated_items=len(items),
        )

    try:
        model = resolve_ollama_model(requested_model)
    except OllamaClientError as exc:
        if not fallback_to_template:
            raise
        return LocalGenerationResult(
            items=items,
            used_mode="template",
            template_generated_items=len(items),
            warnings=[f"Локальная LLM недоступна. Использован резервный шаблонный генератор: {exc}"],
        )

    target_count = min(max(ollama_max_items, 0), len(items))
    if mode == "ollama":
        target_count = len(items)

    enriched: list[AssessmentItemRead] = []
    warnings: list[str] = []
    ollama_count = 0
    template_count = 0
    avoid_texts: list[str] = []

    for index, item in enumerate(items):
        should_enrich = index < target_count
        if not should_enrich:
            enriched.append(item)
            template_count += 1
            avoid_texts.append(item.text)
            continue

        try:
            generated = generate_assessment_item(
                model=model,
                discipline_name=discipline_name,
                section_title=item.section_code,
                assessment_type=item.assessment_type,
                item_type=item.item_type,
                topic=item.topic,
                competency_code=item.competency_code,
                indicator=item.indicator,
                difficulty=item.difficulty,
                rpd_context=_select_relevant_context(source_text, item.topic),
                avoid_texts=avoid_texts,
            )
            updated = item.model_copy(
                update={
                    "text": generated.text,
                    "answer": generated.answer,
                    "criteria": generated.criteria,
                    "source_context": f"РПД: тема «{item.topic}»; локальная модель Ollama: {model}",
                    "source_kind": "ollama",
                }
            )
            enriched.append(updated)
            avoid_texts.append(updated.text)
            ollama_count += 1
        except OllamaClientError as exc:
            if not fallback_to_template:
                raise
            enriched.append(item)
            avoid_texts.append(item.text)
            template_count += 1
            warnings.append(f"Задание по теме «{item.topic}» оставлено шаблонным: {exc}")

    if mode == "ollama" and template_count == 0:
        used_mode = "ollama"
    elif ollama_count > 0:
        used_mode = "hybrid"
    else:
        used_mode = "template"

    if mode == "hybrid" and len(items) > target_count:
        warnings.append(
            f"Локальная модель обработала {target_count} из {len(items)} заданий. Остальные задания сохранены как шаблонные заготовки."
        )

    return LocalGenerationResult(
        items=enriched,
        used_mode=used_mode,
        ollama_model=model,
        ollama_generated_items=ollama_count,
        template_generated_items=template_count,
        warnings=warnings,
    )


def _select_relevant_context(source_text: str, topic: str, max_chars: int = 2800) -> str:
    if not source_text.strip():
        return ""

    normalized_topic_words = {
        word for word in re.findall(r"[A-Za-zА-Яа-яЁё0-9_-]{4,}", topic.lower())
    }
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    ranked: list[tuple[int, str]] = []
    for line in lines:
        words = set(re.findall(r"[A-Za-zА-Яа-яЁё0-9_-]{4,}", line.lower()))
        score = len(words.intersection(normalized_topic_words))
        if score:
            ranked.append((score, line))

    selected = [line for _, line in sorted(ranked, key=lambda item: item[0], reverse=True)[:12]]
    if not selected:
        selected = lines[:18]

    context = "\n".join(selected)
    return context[:max_chars]
