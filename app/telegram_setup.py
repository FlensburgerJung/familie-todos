"""Den Telegram-Webhook anmelden und nachsehen, ob er steht.

    python3 -m app.telegram_setup https://familie-todos.onrender.com
    python3 -m app.telegram_setup --status
    python3 -m app.telegram_setup --aus

Der Bot-Token kommt aus TELEGRAM_BOT_TOKEN, das Webhook-Geheimnis aus
TELEGRAM_WEBHOOK_SECRET. Beides steht in der .env beziehungsweise in den
Umgebungsvariablen des Hosters - dieses Werkzeug liest sie nur.
"""

from __future__ import annotations

import secrets
import sys

from . import telegram
from .llm.base import LLMError, post_json

API = "https://api.telegram.org/bot{token}/{methode}"


def _ruf(methode: str, nutzlast: dict | None = None) -> dict:
    try:
        antwort = post_json(API.format(token=telegram.token(), methode=methode),
                            nutzlast or {}, {}, timeout=20)
    except LLMError as fehler:
        raise SystemExit(f"\n  Telegram nicht erreichbar: {fehler}\n") from fehler
    if not antwort.get("ok"):
        raise SystemExit(f"  Telegram lehnt ab: {antwort.get('description', antwort)}")
    return antwort.get("result", {})


def status() -> None:
    info = _ruf("getWebhookInfo")
    ich = _ruf("getMe")
    print(f"\n  Bot:       @{ich.get('username', '?')} ({ich.get('first_name', '')})")
    print(f"  Webhook:   {info.get('url') or '— keiner gesetzt —'}")
    # Telegram gibt das Geheimnis nicht zurueck - nur, ob hier eines gesetzt ist.
    print(f"  Geheimnis: {'gesetzt' if telegram.secret() else 'FEHLT'}")
    wartend = info.get("pending_update_count", 0)
    print(f"  Wartend:   {wartend}"
          + ("   (werden zugestellt, sobald der Dienst antwortet)" if wartend else ""))
    if info.get("last_error_message"):
        print(f"  Letzter Fehler: {info['last_error_message']}")
    print()


def anmelden(basis: str) -> None:
    basis = basis.rstrip("/")
    if not basis.startswith("https://"):
        raise SystemExit("  Die Adresse muss mit https:// beginnen - Telegram "
                         "stellt nur verschlüsselt zu.")
    geheimnis = telegram.secret()
    if not geheimnis:
        vorschlag = secrets.token_urlsafe(24)
        raise SystemExit(
            "\n  TELEGRAM_WEBHOOK_SECRET fehlt. Ohne das Geheimnis könnte jeder\n"
            "  dem Dienst vortäuschen, Telegram zu sein.\n\n"
            f"  Vorschlag (frisch gewürfelt, nicht von mir gespeichert):\n\n      {vorschlag}\n\n"
            "  In die .env bzw. die Umgebungsvariablen des Hosters eintragen,\n"
            "  dann diesen Befehl noch einmal aufrufen.\n")

    nutzlast = {
        "url": f"{basis}/api/telegram",
        "secret_token": geheimnis,
        # Nur das, was wir auch verarbeiten - spart Zustellungen.
        "allowed_updates": ["message", "channel_post"],
        # Alles, was sich waehrend der Umstellung angesammelt hat, ist alt.
        "drop_pending_updates": True,
    }
    _ruf("setWebhook", nutzlast)
    print(f"\n  Webhook gesetzt auf {nutzlast['url']}")
    status()
    print("  Noch zu tun, falls der Bot in Gruppen schreiben soll:\n"
          "  bei @BotFather /setprivacy -> Disable. Sonst sieht er dort nur\n"
          "  Befehle, keine normalen Nachrichten.\n")


def abmelden() -> None:
    _ruf("deleteWebhook")
    print("\n  Webhook entfernt. Der Bot nimmt nichts mehr entgegen.\n")


def main(argv: list[str]) -> None:
    if not telegram.enabled():
        raise SystemExit(
            "\n  TELEGRAM_BOT_TOKEN ist nicht gesetzt.\n"
            "  Den Token gibt @BotFather in Telegram aus (/newbot).\n")

    if not argv or argv[0] in ("--status", "-s"):
        status()
    elif argv[0] in ("--aus", "--off"):
        abmelden()
    elif argv[0].startswith("-"):
        raise SystemExit(__doc__)
    else:
        anmelden(argv[0])


if __name__ == "__main__":
    main(sys.argv[1:])
