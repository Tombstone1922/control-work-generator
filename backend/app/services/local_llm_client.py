from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LocalLLMSettings:
    enabled: bool
    base_url: str
    model: str
    timeout_seconds: int
    temperature: float
    max_tokens: int


def get_local_llm_settings() -> LocalLLMSettings:
    return LocalLLMSettings(
        enabled=_env_bool("LOCAL_LLM_ENABLED", False),
        base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8081/v1").rstrip("/"),
        model=os.getenv("LOCAL_LLM_MODEL", "qwen3-14b-instruct-q4_k_m"),
        timeout_seconds=int(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "90")),
        temperature=float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("LOCAL_LLM_MAX_TOKENS", "900")),
    )


class LocalLLMClient:
    def __init__(self, settings: LocalLLMSettings | None = None):
        self.settings = settings or get_local_llm_settings()

    def is_enabled(self) -> bool:
        return self.settings.enabled

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.settings.enabled:
            return None
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None

        try:
            response_data = json.loads(raw)
            content = response_data["choices"][0]["message"]["content"]
            return _parse_json_object(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return None


def _parse_json_object(value: str) -> dict[str, Any] | None:
    value = (value or "").strip()
    if not value:
        return None
    if value.startswith("```"):
        value = value.strip("`")
        value = value.replace("json\n", "", 1).strip()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(value[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}
