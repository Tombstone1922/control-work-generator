from __future__ import annotations

import time
from dataclasses import dataclass

from app.services.local_llm_client import LocalLLMClient, get_local_llm_settings


@dataclass
class LocalLLMDiagnosticsResult:
    enabled: bool
    base_url: str
    model: str
    available: bool
    latency_ms: int | None
    json_ok: bool
    sample_text: str
    error: str

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "available": self.available,
            "latency_ms": self.latency_ms,
            "json_ok": self.json_ok,
            "sample_text": self.sample_text,
            "error": self.error,
        }


def check_local_llm() -> LocalLLMDiagnosticsResult:
    settings = get_local_llm_settings()
    if not settings.enabled:
        return LocalLLMDiagnosticsResult(
            enabled=False,
            base_url=settings.base_url,
            model=settings.model,
            available=False,
            latency_ms=None,
            json_ok=False,
            sample_text="",
            error="LOCAL_LLM_ENABLED=false",
        )

    client = LocalLLMClient(settings)
    system_prompt = "Верни строго JSON без markdown. Схема: {\"ok\": true, \"text\": \"...\"}."
    user_prompt = "Проверь связь. Верни JSON с ok=true и коротким текстом: локальная модель доступна."
    started = time.perf_counter()
    data = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    latency_ms = int((time.perf_counter() - started) * 1000)

    if not data:
        return LocalLLMDiagnosticsResult(
            enabled=True,
            base_url=settings.base_url,
            model=settings.model,
            available=False,
            latency_ms=latency_ms,
            json_ok=False,
            sample_text="",
            error="Модель не ответила или вернула невалидный JSON. Проверь llama-server, порт и LOCAL_LLM_BASE_URL.",
        )

    return LocalLLMDiagnosticsResult(
        enabled=True,
        base_url=settings.base_url,
        model=settings.model,
        available=True,
        latency_ms=latency_ms,
        json_ok=bool(data.get("ok", True)),
        sample_text=str(data.get("text") or data.get("message") or data)[:500],
        error="",
    )


def generate_local_llm_sample_task() -> dict:
    settings = get_local_llm_settings()
    if not settings.enabled:
        return {
            "enabled": False,
            "ok": False,
            "error": "LOCAL_LLM_ENABLED=false",
        }

    client = LocalLLMClient(settings)
    system_prompt = """
Ты вузовский преподаватель. Верни строго JSON без markdown.
Схема: {"text":"задание","answer":"эталонный ответ","criteria":["критерий"]}
""".strip()
    user_prompt = """
Сгенерируй одно практическое задание по дисциплине «Разработка веб-приложений».
Тема: «Компонентный подход во frontend-разработке».
Контекст: React, Vue, состояние компонента, свойства, обработчики событий, тестирование интерфейса.
Задание должно быть конкретным и проверяемым.
""".strip()
    data = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    if not data:
        return {
            "enabled": True,
            "ok": False,
            "error": "Модель не ответила или вернула невалидный JSON.",
        }
    return {
        "enabled": True,
        "ok": True,
        "model": settings.model,
        "result": data,
    }
