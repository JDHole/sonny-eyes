"""Sciezki do prawdziwego materialu testowego (klipy, zdjecia, audio).

Repo jest publiczne, wiec zadna sciezka autora nie siedzi w kodzie. Kazdy
material ma klucz; sciezka przychodzi:
1. ze zmiennej srodowiskowej EYES_TEST_<KLUCZ> (np. EYES_TEST_FUJI_FOLDER),
2. albo z pliku tests/material.local.json ({"FUJI_FOLDER": "D:/..."}),
   ktory jest w .gitignore - wzor w tests/material.example.json.
Brak sciezki albo brak pliku na dysku = czesc pomiarowa testu robi SKIP,
nie FAIL: kto sklonuje repo bez materialu, dostaje zielone testy logiki.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

LOCAL_FILE = Path(__file__).resolve().parent / "material.local.json"


def _local() -> dict:
    try:
        return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def material(key: str) -> Path | None:
    """Sciezka materialu `key` albo None, gdy nie jest ustawiona."""
    raw = os.environ.get(f"EYES_TEST_{key}") or _local().get(key)
    return Path(raw) if raw else None


def skip_reason(key: str, path: Path | None) -> str | None:
    """Powod SKIP albo None, gdy material istnieje i mozna mierzyc."""
    if path is None:
        return f"SKIP: brak materialu {key} (ustaw EYES_TEST_{key} albo tests/material.local.json)"
    if not path.exists():
        return f"SKIP: material {key} nie istnieje na dysku: {path}"
    return None
