"""Claude über die Messages API (raw HTTP).

Strukturierte Ausgabe über `output_config.format` - damit kommt garantiert
schema-konformes JSON zurück, kein Nachparsen von Prosa.
"""

from __future__ import annotations

from .base import LLMError, extract_json, post_json

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# Server-seitige Ausweichmodelle: lehnt ein Sicherheitsklassifikator einmal ab
# (stop_reason "refusal"), läuft dieselbe Anfrage im selben Call auf einem
# anderen Modell weiter, statt ohne Ergebnis zu enden.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def classify(system: str, user: str, schema: dict, config: dict) -> dict:
    api_key = config.get("anthropic_api_key")
    if not api_key:
        raise LLMError("Kein Anthropic-API-Key hinterlegt")

    payload = {
        "model": config.get("anthropic_model") or "claude-opus-5",
        "max_tokens": 1500,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        # Einsortieren ist eine kurze Aufgabe - niedriger Aufwand hält die
        # Antwortzeit unten und die Kosten klein.
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": schema},
        },
    }
    headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}

    use_fallbacks = config.get("anthropic_fallbacks", True)
    if use_fallbacks:
        payload["fallbacks"] = "default"
        headers["anthropic-beta"] = FALLBACK_BETA

    try:
        data = post_json(API_URL, payload, headers, timeout=60)
    except LLMError as exc:
        # Kennt der Account das Fallback-Beta nicht, einmal ohne versuchen.
        if use_fallbacks and exc.status == 400:
            payload.pop("fallbacks", None)
            headers.pop("anthropic-beta", None)
            data = post_json(API_URL, payload, headers, timeout=60)
        else:
            raise

    if data.get("stop_reason") == "refusal":
        raise LLMError("Claude hat die Anfrage abgelehnt")
    if data.get("stop_reason") == "max_tokens":
        raise LLMError("Antwort wurde abgeschnitten (max_tokens)")

    for block in data.get("content", []):
        if block.get("type") == "text":
            return extract_json(block.get("text", ""))
    raise LLMError("Keine Textantwort erhalten")
