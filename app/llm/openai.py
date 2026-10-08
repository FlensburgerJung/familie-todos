"""ChatGPT über die Chat-Completions-API (raw HTTP)."""

from __future__ import annotations

from .base import LLMError, extract_json, post_json

API_URL = "https://api.openai.com/v1/chat/completions"


def classify(system: str, user: str, schema: dict, config: dict) -> dict:
    api_key = config.get("openai_api_key")
    if not api_key:
        raise LLMError("Kein OpenAI-API-Key hinterlegt")

    payload = {
        "model": config.get("openai_model") or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "todo_einordnung", "strict": True, "schema": schema},
        },
    }
    data = post_json(API_URL, payload, {"Authorization": f"Bearer {api_key}"}, timeout=60)
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Keine Antwort erhalten")
    return extract_json(choices[0].get("message", {}).get("content", ""))
