"""Sklada schemat raportu, zaokragla liczby, zapisuje JSON."""
from __future__ import annotations

import json
from pathlib import Path


def round_floats(obj, nd: int = 3):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: round_floats(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, nd) for v in obj]
    return obj


def build_report(
    *, id_, projekt, zrodlo, stream, okno_pomiaru, tonalnosc, kolor, ostrosc,
    szum, ruch, plynnosc, montaz, klatki, skopy, flagi, progi, niepewnosc, pomiar,
) -> dict:
    report = {
        "wersja_metryk": "0.2",
        "id": id_,
        "projekt": projekt,
        "zrodlo": zrodlo,
        "stream": stream,
        "okno_pomiaru": okno_pomiaru,
        "tonalnosc": tonalnosc,
        "kolor": kolor,
        "ostrosc": ostrosc,
        "szum": szum,
        "ruch": ruch,
        "plynnosc": plynnosc,
        "montaz": montaz,
        "klatki": klatki,
        "skopy": skopy,
        "flagi_prowizoryczne": flagi,
        "progi_prowizoryczne": progi,
        "werdykty": None,
        "niepewnosc": niepewnosc,
        "pomiar": pomiar,
    }
    return round_floats(report)


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
