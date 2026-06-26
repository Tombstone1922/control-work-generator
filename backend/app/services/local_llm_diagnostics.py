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
    profile: str = "default"

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "profile": self.profile,
            "base_url": self.base_url,
            "model": self.model,
            "available": self.available,
            "latency_ms": self.latency_ms,
            "json_ok": self.json_ok,
            "sample_text": self.sample_text,
            "error": self.error,
        }


def check_local_llm(profile: str | None = None) -> LocalLLMDiagnosticsResult:
    settings = get_local_llm_settings(profile)
    if not settings.enabled:
        return LocalLLMDiagnosticsResult(
            enabled=False,
            profile=settings.profile,
            base_url=settings.base_url,
            model=settings.model,
            available=False,
            latency_ms=None,
            json_ok=False,
            sample_text="",
            error=f"LOCAL_LLM_ENABLED=false для профиля {settings.profile}",
        )

    client = LocalLLMClient(settings)
    system_prompt = "Верни только JSON. Без markdown, без рассуждений, без пояснений. Схема: {\"ok\": true, \"text\": \"...\"}."
    user_prompt = "Ответь ровно одной JSON-строкой: {\"ok\":true,\"text\":\"локальная модель доступна\"}"
    started = time.perf_counter()
    data = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    latency_ms = int((time.perf_counter() - started) * 1000)

    if not data:
        return LocalLLMDiagnosticsResult(
            enabled=True,
            profile=settings.profile,
            base_url=settings.base_url,
            model=settings.model,
            available=False,
            latency_ms=latency_ms,
            json_ok=False,
            sample_text=client.last_raw_content[:500],
            error="Модель не ответила или вернула невалидный JSON. Проверь llama-server, порт и LOCAL_LLM_BASE_URL.",
        )

    return LocalLLMDiagnosticsResult(
        enabled=True,
        profile=settings.profile,
        base_url=settings.base_url,
        model=settings.model,
        available=True,
        latency_ms=latency_ms,
        json_ok=bool(data.get("ok", True)),
        sample_text=str(data.get("text") or data.get("message") or data)[:500],
        error="",
    )


def generate_local_llm_sample_task(profile: str | None = None) -> dict:
    settings = get_local_llm_settings(profile)
    if not settings.enabled:
        return {
            "enabled": False,
            "profile": settings.profile,
            "ok": False,
            "error": f"LOCAL_LLM_ENABLED=false для профиля {settings.profile}",
        }

    client = LocalLLMClient(settings)
    system_prompt = """
Верни только валидный JSON. Без markdown, без рассуждений, без пояснений.
Не используй одинарные кавычки. Не добавляй текст до или после JSON.
Схема: {"text":"задание","answer":"эталонный ответ","criteria":["критерий 1","критерий 2"]}
""".strip()
    user_prompt = """
Сформируй JSON для одного практического задания.
Дисциплина: Разработка веб-приложений.
Тема: Компонентный подход во frontend-разработке.
Контекст: React, Vue, состояние компонента, свойства, обработчики событий, тестирование интерфейса.
Ответ должен быть ровно одним JSON-объектом.
""".strip()
    data = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    if not data:
        return {
            "enabled": True,
            "profile": settings.profile,
            "ok": False,
            "raw_content": client.last_raw_content[:1000],
            "error": "Модель ответила, но JSON не удалось распознать.",
        }
    return {
        "enabled": True,
        "profile": settings.profile,
        "ok": True,
        "model": settings.model,
        "result": data,
    }
