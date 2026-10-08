"""Liest eine .env-Datei im Projektordner.

Bewusst ohne Zusatzpaket: Die Datei hat ein simples Format, und die App soll
zuhause weiterhin ohne Installation starten.

Bereits gesetzte Umgebungsvariablen gewinnen. So überschreibt eine lokal
liegengebliebene .env niemals die echten Einstellungen eines Servers.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load(path: Path | None = None) -> list[str]:
    """Lädt die Datei und gibt die Namen der gesetzten Variablen zurück."""
    target = path or ENV_PATH
    if not target.exists():
        return []

    loaded = []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = _unquote(value)
        if not name or not value:
            continue
        # Was in der Umgebung steht, bleibt stehen.
        if name in os.environ and os.environ[name]:
            continue
        os.environ[name] = value
        loaded.append(name)
    return loaded
