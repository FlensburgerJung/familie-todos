"""Mistral über die Chat-Completions-API (raw HTTP).

Mistral kennt zwei Wege zu verlässlichem JSON: `json_schema` erzwingt das
Schema beim Dekodieren, `json_object` garantiert nur gültiges JSON. Die genaue
Verschachtelung von `json_schema` ist nicht öffentlich dokumentiert, deshalb
wird sie einmal ausprobiert und bei Ablehnung dauerhaft auf `json_object`
umgeschaltet - statt sich auf eine geratene Form zu verlassen.
"""

from __future__ import annotations

import json

from .base import LLMError, extract_json, post_json

API_URL = "https://api.mistral.ai/v1/chat/completions"

# Merkt sich, was der Server akzeptiert hat: "schema", "object" oder None
# (noch nicht ausprobiert). Spart den Fehlversuch bei jedem Einwurf.
_mode: str | None = None


def _payload(system: str, user: str, schema: dict, model: str, mode: str) -> dict:
    if mode == "schema":
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "todo_einordnung", "schema": schema, "strict": True},
        }
        system_text = system
    else:
        # Ohne erzwungenes Schema muss das Format im Prompt stehen.
        response_format = {"type": "json_object"}
        system_text = (
            f"{system}\n\nAntworte ausschließlich mit JSON nach diesem Schema:\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user},
        ],
        "response_format": response_format,
        "temperature": 0.2,
    }


def _read(data: dict) -> dict:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Keine Antwort erhalten")
    return extract_json(choices[0].get("message", {}).get("content", ""))


def classify(system: str, user: str, schema: dict, config: dict) -> dict:
    global _mode

    api_key = config.get("mistral_api_key")
    if not api_key:
        raise LLMError("Kein Mistral-API-Key hinterlegt")

    model = config.get("mistral_model") or "mistral-small-latest"
    headers = {"Authorization": f"Bearer {api_key}"}

    for mode in (["schema", "object"] if _mode is None else [_mode]):
        try:
            data = post_json(API_URL, _payload(system, user, schema, model, mode),
                             headers, timeout=60)
        except LLMError as exc:
            # 400/422 heißt: dieses Format akzeptiert der Server nicht.
            if mode == "schema" and exc.status in (400, 422):
                continue
            raise
        _mode = mode
        return _read(data)

    raise LLMError("Mistral hat kein nutzbares Antwortformat akzeptiert")
