"""Lokaler Start - zuhause auf dem eigenen Rechner.

Nutzt den WSGI-Server aus der Standardbibliothek, damit hier nichts
installiert werden muss. Online startet gunicorn dieselbe App aus `app.wsgi`.
"""

from __future__ import annotations

import argparse
import os
import socket
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from . import auth, classify, config, db, store
from .wsgi import application, ensure_booted


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Mehrere Geräte gleichzeitig - ohne Threads blockiert eine langsame
    Modellantwort alle anderen."""

    daemon_threads = True
    allow_reuse_address = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, fmt, *args):
        # Nur Fehler protokollieren, nicht jeden Abruf.
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Familien-ToDo-Server (lokal)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8765))
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"),
                        help="0.0.0.0 = auch von Handys im WLAN erreichbar")
    args = parser.parse_args()

    # Der lokale Start darf auf die Datenbank warten - anders als beim Hoster,
    # wo ein blockierter Start bedeutet, dass der Port nie aufgeht. Ohne das
    # hier scheitert der erste Start mit einer frischen Datei an fehlenden
    # Tabellen.
    ensure_booted()

    cfg = config.load()
    chain = classify.provider_chain(cfg) + ["heuristic"]
    calendar_token = db.get_settings().get("calendar_token", "")
    ip = local_ip()

    server = make_server(args.host, args.port, application,
                         server_class=ThreadingWSGIServer, handler_class=QuietHandler)

    lines = [
        "", "  Familie ToDos läuft",
        f"  Speicher:   {store.describe()}",
        f"  Einordnung: {' -> '.join(chain)}",
        f"  Anmeldung:  {'Passwort nötig' if auth.enabled() else 'aus (nur Heimnetz)'}",
        "", f"  Hier:       http://localhost:{args.port}",
    ]
    if args.host == "0.0.0.0":
        lines.append(f"  Im WLAN:    http://{ip}:{args.port}")
    feed = f"http://{ip}:{args.port}/calendar.ics"
    if auth.enabled():
        feed += f"?token={calendar_token}"
    lines += [f"  Kalender:   {feed}", "", "  Beenden mit Strg+C", ""]
    # Ausdrücklich leeren: sonst hängt die Meldung im Puffer, sobald die
    # Ausgabe in eine Datei geht (etwa beim Start über launchd).
    print("\n".join(lines), flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Tschüss.")
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
