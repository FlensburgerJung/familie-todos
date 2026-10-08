"""Mistral über die Chat-Completions-API (raw HTTP).

JSON-Modus plus Schema im Prompt - das funktioniert über alle Mistral-Modelle
hinweg, auch die kleineren.
"""

from __future__ import annotations

import json

from .base import LLMError, extract_json, post_json

API_URL = "https://api.mistral.ai/v1/chat/completions"


def classify(system: str, user: str, schema: dict, config: dict) -> dict:
    api_key = config.get("mistral_api_key")
    if not api_key:
        raise LLMError("Kein Mistral-API-Key hinterlegt")

    system_with_schema = (
        f"{system}\n\nAntworte ausschließlich mit JSON nach diesem Schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
    payload = {
        "model": config.get("mistral_model") or "mistral-large-latest",
        "messages": [
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    data = post_json(API_URL, payload, {"Authorization": f"Bearer {api_key}"}, timeout=60)
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Keine Antwort erhalten")
    return extract_json(choices[0].get("message", {}).get("content", ""))
