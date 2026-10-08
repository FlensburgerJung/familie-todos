"""Lokales Modell über Ollama - der Offline-Weg.

Ollama nimmt ein JSON-Schema direkt in `format` entgegen und erzwingt es beim
Dekodieren, deshalb braucht es hier keinen Schema-Text im Prompt.

Zwei Eigenheiten, die in der Praxis wehtun und hier abgefangen werden:
Reasoning-Modelle (gemma4, qwen3 ...) verbrauchen ihr ganzes Token-Budget mit
Nachdenken und liefern dann eine leere Antwort - deshalb `think: False`. Und
ohne `num_predict` kann eine entgleiste Generierung bis zum Timeout laufen.
"""

from __future__ import annotations

from .base import LLMError, extract_json, post_json

# Einsortieren braucht keine langen Gedankengänge; das Budget reicht für die
# Antwort mit Reserve und begrenzt gleichzeitig Ausreißer.
MAX_TOKENS = 1200
KEEP_ALIVE = "30m"  # Modell geladen halten, spart das Nachladen bei jedem Einwurf


def _payload(system: str, user: str, schema: dict, model: str, think: bool | None) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": schema,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.1, "num_predict": MAX_TOKENS},
    }
    if think is not None:
        payload["think"] = think
    return payload


def classify(system: str, user: str, schema: dict, config: dict) -> dict:
    base_url = (config.get("ollama_url") or "http://localhost:11434").rstrip("/")
    model = config.get("ollama_model") or "gemma4:12b-mlx"
    url = f"{base_url}/api/chat"

    try:
        data = post_json(url, _payload(system, user, schema, model, think=False), {}, timeout=120)
    except LLMError as exc:
        # Ältere Ollama-Versionen kennen `think` nicht.
        if exc.status == 400:
            data = post_json(url, _payload(system, user, schema, model, None), {}, timeout=120)
        else:
            raise

    message = data.get("message") or {}
    content = (message.get("content") or "").strip()

    if not content:
        # Denkt das Modell trotzdem, steckt das JSON manchmal im Denkteil.
        thinking = (message.get("thinking") or "").strip()
        if thinking and "{" in thinking:
            return extract_json(thinking)
        if data.get("done_reason") == "length":
            raise LLMError(
                f"{model} hat das Token-Budget aufgebraucht, ohne zu antworten. "
                "Ein kleineres oder nicht-denkendes Modell funktioniert hier besser."
            )
        raise LLMError("Ollama lieferte keine Antwort")

    return extract_json(content)


def is_available(config: dict) -> bool:
    import json as _json
    import urllib.error
    import urllib.request

    base_url = (config.get("ollama_url") or "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as response:
            _json.loads(response.read().decode("utf-8"))
        return True
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
