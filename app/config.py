"""Einstellungen aus der Datenbank plus Zugangsdaten.

Umgebungsvariablen haben Vorrang vor der Schlüsseldatei - so kann man Keys
setzen, ohne sie irgendwo abzulegen.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from . import db

SECRETS_PATH = Path(__file__).resolve().parent.parent / "data" / "secrets.json"

KEY_FIELDS = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "mistral_api_key": "MISTRAL_API_KEY",
}


def _read_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_secrets(values: dict) -> None:
    """Keys speichern. Leerer Wert löscht den Eintrag."""
    secrets = _read_secrets()
    for field in KEY_FIELDS:
        if field in values:
            value = (values[field] or "").strip()
            if value:
                secrets[field] = value
            else:
                secrets.pop(field, None)
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
    # Nur für den eigenen Benutzer lesbar.
    SECRETS_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def load() -> dict:
    config = dict(db.get_settings())
    secrets = _read_secrets()
    for field, env_var in KEY_FIELDS.items():
        config[field] = os.environ.get(env_var) or secrets.get(field, "")
    config["anthropic_fallbacks"] = True
    return config


def key_status() -> dict:
    """Woher ein Key kommt - ohne ihn preiszugeben."""
    secrets = _read_secrets()
    status = {}
    for field, env_var in KEY_FIELDS.items():
        if os.environ.get(env_var):
            status[field] = "env"
        elif secrets.get(field):
            status[field] = "gespeichert"
        else:
            status[field] = ""
    return status
