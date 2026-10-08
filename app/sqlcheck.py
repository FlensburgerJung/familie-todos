"""Prüft jedes SQL im Projekt auf Postgres-Tauglichkeit - ohne Postgres.

    python3 -m app.sqlcheck

Sinnvoll vor jedem Deployment: zuhause läuft SQLite und schluckt Dinge, die
Postgres ablehnt. Dieser Test findet das, bevor Render es tut.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Konstrukte, die SQLite kennt und Postgres nicht
FORBIDDEN = {
    r"\bAUTOINCREMENT\b": "AUTOINCREMENT gibt es in Postgres nicht",
    r"\bPRAGMA\b": "PRAGMA ist SQLite-spezifisch",
    r"INSERT\s+OR\s+(IGNORE|REPLACE)": "INSERT OR ... -> ON CONFLICT verwenden",
    r"\bdate\s*\(\s*'now'": "date('now') ist SQLite-spezifisch",
    r"\bdatetime\s*\(\s*'now'": "datetime('now') ist SQLite-spezifisch",
    r"\bstrftime\s*\(": "strftime() ist SQLite-spezifisch",
    r"\bREAL\b": "REAL -> DOUBLE PRECISION",
    r"\bIFNULL\s*\(": "IFNULL -> COALESCE",
    r"\bGLOB\b": "GLOB ist SQLite-spezifisch",
}

SQL_WORDS = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER)\b", re.I)


def sql_literals(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_WORDS.search(node.value):
                yield node.lineno, node.value


def main() -> int:
    problems, checked = [], 0
    for path in sorted(ROOT.glob("*.py")):
        for lineno, text in sql_literals(path):
            parts = [p.strip() for p in text.split(";") if p.strip()] if ";" in text else [text]
            for part in parts:
                checked += 1
                for pattern, why in FORBIDDEN.items():
                    if re.search(pattern, part, re.I):
                        problems.append(f"{path.name}:{lineno} — {why}\n      {part[:80]}")

    print(f"\n  {checked} SQL-Anweisungen geprüft")
    if problems:
        for problem in problems:
            print("  ✗", problem)
        print()
        return 1
    print("  ✓ keine SQLite-Eigenheiten gefunden\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
