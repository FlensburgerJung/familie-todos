"""Familien-ToDo-App.

Die .env wird hier geladen, nicht später: `store` entscheidet anhand von
DATABASE_URL über die Datenbank, und das muss vor dem ersten Zugriff feststehen.
"""

from . import dotenv as _dotenv

LOADED_ENV = _dotenv.load()
