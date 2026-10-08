"""Gemeinsamer HTTP-Unterbau für alle LLM-Anbieter.

Bewusst ohne SDKs: Die App soll ohne `pip install` starten, und vier Anbieter
über einen einzigen, gleich aussehenden HTTP-Aufruf sind leichter zu warten
als vier verschiedene Client-Bibliotheken.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

_context = None


def _ssl_context():
    """TLS-Kontext mit verlässlichen Wurzelzertifikaten.

    Python bringt auf macOS keine mit; ohne certifi scheitert jeder Aufruf an
    Mistral, Anthropic oder OpenAI mit "unable to get local issuer certificate".
    Einmal gebaut und wiederverwendet.
    """
    global _context
    if _context is None:
        try:
            import certifi
            _context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _context = ssl.create_default_context()
    return _context


class LLMError(RuntimeError):
    """Anbieter nicht erreichbar, abgelehnt oder Antwort unbrauchbar."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise LLMError(f"HTTP {exc.code}: {detail}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "CERTIFICATE_VERIFY_FAILED" in reason:
            raise LLMError(
                "TLS-Zertifikat nicht prüfbar. Python auf macOS bringt keine "
                "Wurzelzertifikate mit - mit `pip3 install --user certifi` "
                "beheben oder die App aus der .venv starten."
            ) from exc
        raise LLMError(f"Nicht erreichbar: {reason}") from exc
    except TimeoutError as exc:
        raise LLMError("Zeitüberschreitung") from exc


def extract_json(text: str) -> dict:
    """JSON aus einer Modellantwort holen, auch wenn Prosa drumherum steht.

    Kleinere lokale Modelle verpacken ihre Antwort gern in einen Codeblock,
    schreiben "json" davor oder verdoppeln die äußeren Klammern.
    """
    text = (text or "").strip()

    if "```" in text:
        parts = text.split("```")
        # Der längste Abschnitt zwischen den Zäunen ist der Inhalt.
        text = max(parts[1::2] or parts, key=len).strip()
    text = text.removeprefix("json").strip()

    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        inner = text[start:end + 1]
        candidates.append(inner)
        # "{{...}}" -> "{...}"
        if inner.startswith("{{") and inner.endswith("}}"):
            candidates.append(inner[1:-1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise LLMError(f"Antwort war kein gültiges JSON: {text[:200]}")
