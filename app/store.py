"""Datenbankzugriff für zwei Betriebsarten.

Zuhause: SQLite in einer Datei, ohne jede Abhängigkeit.
Online:  Postgres (z. B. Neon), sobald DATABASE_URL gesetzt ist.

Derselbe SQL-Text läuft auf beiden. Möglich wird das dadurch, dass pg8000
auf den Fragezeichen-Platzhalter umgestellt wird und das Schema nur Typen und
Konstrukte verwendet, die beide Datenbanken kennen (TEXT, INTEGER, DOUBLE
PRECISION, ON CONFLICT). Es gibt also keine zweite SQL-Variante zu pflegen.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "todos.db"

_local = threading.local()


class StoreError(RuntimeError):
    pass


def database_url() -> str:
    return (os.environ.get("DATABASE_URL") or "").strip()


def backend() -> str:
    """'postgres', sobald eine Datenbank-URL gesetzt ist, sonst 'sqlite'."""
    return "postgres" if database_url() else "sqlite"


# --- Verbindungsaufbau --------------------------------------------------

def _connect_sqlite():
    import sqlite3

    path = Path(os.environ.get("SQLITE_PATH") or DEFAULT_SQLITE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ssl_context():
    """TLS-Kontext mit verlässlichen Wurzelzertifikaten.

    Python bringt auf macOS keine mit, deshalb scheitert die Prüfung dort mit
    "unable to get local issuer certificate". certifi liefert sie als Paket -
    plattformunabhängig und auch auf dem Server die sichere Variante.
    """
    import ssl

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        # Ohne certifi die Zertifikate des Systems nehmen. Auf Linux-Servern
        # reicht das meist, auf macOS in der Regel nicht.
        return ssl.create_default_context()


def _connect_postgres():
    try:
        import pg8000.dbapi
    except ImportError as exc:  # pragma: no cover - nur ohne installiertes Paket
        raise StoreError(
            "DATABASE_URL ist gesetzt, aber der Treiber pg8000 fehlt. "
            "Installieren mit: pip install -r requirements.txt"
        ) from exc

    import ssl

    # Fragezeichen statt %s - damit ist das SQL identisch zur SQLite-Variante.
    pg8000.dbapi.paramstyle = "qmark"

    url = urlparse(database_url())
    if url.scheme not in ("postgres", "postgresql"):
        raise StoreError(f"DATABASE_URL muss mit postgres:// beginnen, nicht {url.scheme}://")

    options = parse_qs(url.query)
    sslmode = (options.get("sslmode") or ["require"])[0]
    context = None if sslmode == "disable" else _ssl_context()

    conn = pg8000.dbapi.connect(
        user=unquote(url.username or ""),
        password=unquote(url.password or ""),
        host=url.hostname or "localhost",
        port=url.port or 5432,
        database=(url.path or "/").lstrip("/") or "postgres",
        ssl_context=context,
        timeout=15,
        application_name="familie-todos",
    )
    return conn


def connect():
    """Verbindung des aktuellen Threads, bei Bedarf neu aufgebaut."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    conn = _connect_postgres() if backend() == "postgres" else _connect_sqlite()
    _local.conn = conn
    return conn


def close() -> None:
    conn = getattr(_local, "conn", None)
    _local.conn = None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


# --- Abfragen -----------------------------------------------------------

# Neon fährt die Datenbank nach einigen Minuten Ruhe herunter; die erste
# Anfrage danach läuft in eine tote Verbindung. Einmal neu verbinden und
# wiederholen, statt den Benutzer einen Fehler sehen zu lassen.
#
# Auf die Fehlerklasse zu prüfen ist verlässlicher als auf Textbausteine:
# pg8000 meldet eine abgerissene Verbindung als InterfaceError("network
# error") - ein Wortlaut, den keine noch so lange Stichwortliste zuverlässig
# trifft. Die Liste bleibt als Ergänzung für Treiber, die anders melden.
_RETRYABLE_TYPES = ("InterfaceError", "OperationalError", "SSLEOFError",
                    "SSLError", "SSLZeroReturnError", "ConnectionResetError",
                    "BrokenPipeError", "TimeoutError")

_RETRYABLE_WORDS = ("closed", "connection", "broken pipe", "terminat", "eof",
                    "reset", "ssl", "timeout", "not connected", "network")


def _is_connection_error(exc: Exception) -> bool:
    for klass in type(exc).__mro__:
        if klass.__name__ in _RETRYABLE_TYPES:
            return True
    return any(word in str(exc).lower() for word in _RETRYABLE_WORDS)


def _rows_from(cursor) -> list[dict]:
    if cursor.description is None:
        return []
    names = []
    for column in cursor.description:
        name = column[0]
        names.append(name.decode() if isinstance(name, bytes) else name)
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _run(sql: str, params, want_rows: bool, commit: bool):
    for attempt in (1, 2):
        conn = connect()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = _rows_from(cursor) if want_rows else []
            count = cursor.rowcount
            cursor.close()
            if commit:
                conn.commit()
            return rows, count
        except Exception as exc:
            if _is_connection_error(exc):
                close()          # tote Verbindung nie weiterverwenden
                if attempt == 1:
                    continue
            else:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise


def query(sql: str, params=()) -> list[dict]:
    rows, _ = _run(sql, params, want_rows=True, commit=False)
    return rows


def one(sql: str, params=()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=()) -> int:
    _, count = _run(sql, params, want_rows=False, commit=True)
    return count


def execute_many(statements: list[tuple[str, tuple]]) -> None:
    """Mehrere Anweisungen in einer Transaktion."""
    for attempt in (1, 2):
        conn = connect()
        try:
            cursor = conn.cursor()
            for sql, params in statements:
                cursor.execute(sql, tuple(params))
            cursor.close()
            conn.commit()
            return
        except Exception as exc:
            if _is_connection_error(exc):
                close()
                if attempt == 1:
                    continue
            else:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise


def script(sql: str) -> None:
    """Mehrere durch Semikolon getrennte Anweisungen ausführen (Schema-Aufbau)."""
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    execute_many([(statement, ()) for statement in statements])


def describe() -> str:
    """Kurzbeschreibung fürs Log und die Diagnose."""
    if backend() == "postgres":
        host = urlparse(database_url()).hostname or "?"
        return f"Postgres auf {host}"
    return f"SQLite unter {os.environ.get('SQLITE_PATH') or DEFAULT_SQLITE_PATH}"
