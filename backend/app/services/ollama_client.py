from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class OllamaClientError(RuntimeError):
    pass


@dataclass
class OllamaStatus:
    available: bool
    base_url: str
    models: list[str]
    default_model: str
    error: str = ""


@dataclass
class OllamaAssessmentItem:
    text: str
    answer: str
    criteria: list[str]


def get_ollama_base_url() -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    _validate_local_endpoint(base_url)
    return base_url


def get_ollama_status() -> OllamaStatus:
    try:
        base_url = get_ollama_base_url()
        payload = _request_json("GET", f"{base_url}/api/tags", timeout=4)
        models = [item.get("name") or item.get("model") for item in payload.get("models", [])]
        models = [model for model in models if isinstance(model, str) and model.strip()]
        default_model = _choose_default_model(models)
        return OllamaStatus(
            available=True,
            base_url=base_url,
            models=models,
            default_model=default_model,
        )
    except OllamaClientError as exc:
        return OllamaStatus(
            available=False,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
            models=[],
            default_model=os.getenv("OLLAMA_MODEL", "").strip(),
            error=str(exc),
        )


def resolve_ollama_model(requested_model: str | None = None) -> str:
    status = get_ollama_status()
    if not status.available:
        raise OllamaClientError(status.error or "Локальный сервер Ollama недоступен.")

    requested = (requested_model or "").strip()
    if requested:
        if requested not in status.models:
            raise OllamaClientError(
                f"Модель «{requested}» не найдена в Ollama. Установленные модели: {', '.join(status.models) or 'нет моделей'}."
            )
        return requested

    if status.default_model:
        return status.default_model
    raise OllamaClientError("В Ollama не установлено ни одной модели.")


def generate_assessment_item(
    *,
    model: str,
    discipline_name: str,
    section_title: str,
    assessment_type: str,
    item_type: str,
    topic: str,
    competency_code: str,
    indicator: str,
    difficulty: str,
    rpd_context: str,
    avoid_texts: list[str],
) -> OllamaAssessmentItem:
    base_url = get_ollama_base_url()
    prompt = _build_prompt(
        discipline_name=discipline_name,
        section_title=section_title,
        assessment_type=assessment_type,
        item_type=item_type,
        topic=topic,
        competency_code=competency_code,
        indicator=indicator,
        difficulty=difficulty,
        rpd_context=rpd_context,
        avoid_texts=avoid_texts,
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты проектировщик оценочных материалов образовательной организации. "
                    "Формируй содержательные задания строго по переданному контексту РПД. "
                    "Не добавляй сведения, которых нет в контексте. Верни только JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.25,
            "num_predict": 900,
        },
        "keep_alive": "10m",
    }
    response = _request_json(
        "POST",
        f"{base_url}/api/chat",
        payload=payload,
        timeout=int(os.getenv("OLLAMA_GENERATION_TIMEOUT_SECONDS", "180")),
    )
    content = response.get("message", {}).get("content", "")
    data = _parse_json_content(content)

    text = _as_non_empty_string(data.get("text"), "формулировка задания")
    answer = _as_non_empty_string(data.get("answer"), "эталонный ответ")
    raw_criteria = data.get("criteria", [])
    criteria = [str(item).strip() for item in raw_criteria if str(item).strip()] if isinstance(raw_criteria, list) else []
    if not criteria:
        raise OllamaClientError("Локальная модель не вернула критерии оценивания.")

    return OllamaAssessmentItem(text=text, answer=answer, criteria=criteria[:6])


def _build_prompt(
    *,
    discipline_name: str,
    section_title: str,
    assessment_type: str,
    item_type: str,
    topic: str,
    competency_code: str,
    indicator: str,
    difficulty: str,
    rpd_context: str,
    avoid_texts: list[str],
) -> str:
    duplicates = "\n".join(f"- {item}" for item in avoid_texts[-8:]) or "- отсутствуют"
    return f"""
Сформируй одно оценочное задание для фонда оценочных средств.

Дисциплина: {discipline_name}
Раздел ФОС: {section_title}
Вид контроля: {assessment_type}
Тип задания: {item_type}
Тема: {topic}
Компетенция: {competency_code or 'не указана'}
Индикатор: {indicator or 'не указан'}
Уровень сложности: {difficulty}

Контекст из РПД:
{rpd_context or 'Контекст не найден. Используй только тему и параметры задания.'}

Избегай повторения формулировок:
{duplicates}

Требования:
1. Формулировка должна проверять знания или умения по указанной теме.
2. Задание должно соответствовать виду контроля и уровню сложности.
3. Эталонный ответ должен быть содержательным, но компактным.
4. Критерии оценивания должны быть проверяемыми.
5. Не добавляй markdown и пояснения вне JSON.

Верни JSON строго такого вида:
{{
  "text": "формулировка задания",
  "answer": "эталонный ответ",
  "criteria": ["критерий 1", "критерий 2", "критерий 3"]
}}
""".strip()


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(url=url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise OllamaClientError(f"Ollama вернула HTTP {exc.code}: {details[:400]}") from exc
    except URLError as exc:
        raise OllamaClientError(f"Не удалось подключиться к Ollama: {exc.reason}") from exc
    except TimeoutError as exc:
        raise OllamaClientError("Превышено время ожидания ответа Ollama.") from exc

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaClientError("Ollama вернула некорректный JSON.") from exc
    if not isinstance(value, dict):
        raise OllamaClientError("Ollama вернула неожиданный формат ответа.")
    return value


def _parse_json_content(content: str) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise OllamaClientError("Локальная модель вернула пустой ответ.")
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise OllamaClientError("Не удалось разобрать JSON локальной модели.") from exc
    if not isinstance(value, dict):
        raise OllamaClientError("Локальная модель вернула JSON неверной структуры.")
    return value


def _as_non_empty_string(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise OllamaClientError(f"Локальная модель не вернула поле: {field_name}.")
    return text


def _choose_default_model(models: list[str]) -> str:
    configured = os.getenv("OLLAMA_MODEL", "").strip()
    if configured and configured in models:
        return configured
    return models[0] if models else configured


def _validate_local_endpoint(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OllamaClientError("OLLAMA_BASE_URL должен быть корректным HTTP-адресом.")
    if os.getenv("OLLAMA_ALLOW_PUBLIC_ENDPOINT", "false").lower() in {"1", "true", "yes"}:
        return

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or "." not in hostname:
        return
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise OllamaClientError(
            "Публичный адрес Ollama запрещен. Используйте localhost, адрес локальной сети или задайте OLLAMA_ALLOW_PUBLIC_ENDPOINT=true."
        ) from exc
    if not (address.is_loopback or address.is_private):
        raise OllamaClientError(
            "Публичный адрес Ollama запрещен. Используйте локальный сервер или задайте OLLAMA_ALLOW_PUBLIC_ENDPOINT=true."
        )
