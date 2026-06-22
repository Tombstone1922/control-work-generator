from __future__ import annotations

import ast
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


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
        self.last_raw_content = ""

    def is_enabled(self) -> bool:
        return self.settings.enabled

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.settings.enabled:
            return None
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": _no_think(system_prompt)},
                {"role": "user", "content": _no_think(user_prompt)},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "response_format": {"type": "json_object"},
        }
        raw = self._post_chat(payload)
        if raw is None:
            payload.pop("response_format", None)
            raw = self._post_chat(payload)
        if raw is None:
            return None

        try:
            response_data = json.loads(raw)
            content = response_data["choices"][0]["message"]["content"]
            self.last_raw_content = str(content or "")
            return _parse_json_object(self.last_raw_content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            self.last_raw_content = raw[:2000]
            return None

    def _post_chat(self, payload: dict[str, Any]) -> str | None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError):
            return None


def _no_think(prompt: str) -> str:
    prompt = (prompt or "").strip()
    return f"/no_think\n{prompt}"


def _parse_json_object(value: str) -> dict[str, Any] | None:
    value = _strip_thinking(value or "").strip()
    if not value:
        return None
    if value.startswith("```"):
        value = value.strip("`")
        value = value.replace("json\n", "", 1).strip()
    candidates = [value]
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        candidates.append(value[start : end + 1])

    for candidate in candidates:
        candidate = candidate.strip()
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        try:
            data = ast.literal_eval(candidate)
            return data if isinstance(data, dict) else None
        except (SyntaxError, ValueError):
            pass
    return None


def _strip_thinking(value: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"^.*?</think>", "", value, flags=re.DOTALL | re.IGNORECASE)
    return value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}
