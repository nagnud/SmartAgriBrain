from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def is_placeholder_secret(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        not lowered
        or lowered.startswith("your_")
        or "api_key_here" in lowered
        or lowered in {"your-deepseek-api-key", "sk-xxxx"}
    )


def deepseek_api_key() -> str:
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return "" if is_placeholder_secret(value) else value


def deepseek_configured() -> bool:
    return bool(deepseek_api_key())


def deepseek_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip() or DEFAULT_DEEPSEEK_MODEL


def deepseek_chat_completion_url() -> str:
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).strip() or DEFAULT_DEEPSEEK_BASE_URL
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def deepseek_timeout_seconds(default: float = 60.0) -> float:
    raw = os.getenv("DEEPSEEK_TIMEOUT_SECONDS", str(default)).strip()
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return default


def strip_code_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        last_fence = text.rfind("```")
        if first_newline >= 0 and last_fence > first_newline:
            return text[first_newline + 1:last_fence].strip()
    return text


def extract_chat_content(result: Dict[str, Any]) -> str:
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message["content"])
            if first.get("text") is not None:
                return str(first["text"])

    output = result.get("output")
    if isinstance(output, dict):
        if output.get("text") is not None:
            return str(output["text"])
        output_choices = output.get("choices")
        if isinstance(output_choices, list) and output_choices:
            first = output_choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and message.get("content") is not None:
                    return str(message["content"])

    raise ValueError("DeepSeek response missing message content")


def call_deepseek_chat(
    messages: List[Dict[str, str]],
    *,
    max_tokens: int,
    timeout_seconds: Optional[float] = None,
    temperature: float = 0.3,
    response_format: Optional[Dict[str, str]] = None,
) -> str:
    api_key = deepseek_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    body: Dict[str, Any] = {
        "model": deepseek_model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        body["response_format"] = response_format

    thinking_mode = os.getenv("DEEPSEEK_THINKING", "disabled").strip().lower()
    if thinking_mode in {"enabled", "disabled", "auto"}:
        body["thinking"] = {"type": thinking_mode}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout_seconds or deepseek_timeout_seconds()) as client:
        try:
            response = client.post(deepseek_chat_completion_url(), headers=headers, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if "thinking" not in body or error.response.status_code not in {400, 422}:
                raise
            retry_body = dict(body)
            retry_body.pop("thinking", None)
            response = client.post(deepseek_chat_completion_url(), headers=headers, json=retry_body)
            response.raise_for_status()
        return extract_chat_content(response.json())
