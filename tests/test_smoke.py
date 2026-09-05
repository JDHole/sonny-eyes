"""Test dymny (bramka). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_smoke.py

Sprawdza raporty DSCF3236 (Fuji) i GX010042 (GoPro) w projekcie
"Canarian Tweety EP03": komplet kluczy najwyzszego poziomu, zakresy 0..1 i
monotonicznosc percentyli tonalnosci, obecnosc i rozmiar 4 PNG, oraz
zgodnosc kamera/LUT z oczekiwaniem.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes.config import load_config  # noqa: E402

PROJECT = "Canarian Tweety EP03"
CASES = [
    {"id": "DSCF3236", "kamera": "Fuji"},
    {"id": "GX010042", "kamera": "GoPro"},
]

TOP_KEYS = [
    "wersja_metryk", "id", "projekt", "zrodlo", "stream", "okno_pomiaru",
    "tonalnosc", "kolor", "ostrosc", "szum", "ruch", "plynnosc", "montaz",
    "klatki", "skopy", "flagi_prowizoryczne", "progi_prowizoryczne",
    "werdykty", "niepewnosc", "pomiar",
]

MAX_PNG_BYTES = 500 * 1024

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    cfg = load_config(REPO_ROOT / "config.toml")
    report_dir = Path(cfg.vault) / "40_Pracownie" / "Analog Studio" / "Projekty" / PROJECT / "Color" / "reports"
    cache_root = Path(cfg.cache_root)

    for case in CASES:
        id_ = case["id"]
        report_path = report_dir / f"{id_}.json"
        check(report_path.exists(), f"{id_}: brak raportu {report_path}")
        if not report_path.exists():
            continue

        data = json.loads(report_path.read_text(encoding="utf-8"))

        for key in TOP_KEYS:
            check(key in data, f"{id_}: brak klucza najwyzszego poziomu '{key}'")

        tonalnosc = data.get("tonalnosc", {})
        percentile_keys = ["p1", "p5", "p50", "p95", "p99"]
        values = {}
        for pk in percentile_keys:
            v = tonalnosc.get(pk)
            values[pk] = v
            check(v is not None and 0.0 <= v <= 1.0, f"{id_}: tonalnosc.{pk}={v} poza zakresem 0..1")
        if all(values[pk] is not None for pk in percentile_keys):
            check(
                values["p1"] <= values["p5"] <= values["p50"] <= values["p95"] <= values["p99"],
                f"{id_}: percentyle nie rosna monotonicznie: {values}",
            )

        for fr in data.get("klatki", []):
            p = cache_root / fr["plik"]
            check(p.exists(), f"{id_}: brak pliku klatki {p}")
            if p.exists():
                check(p.stat().st_size <= MAX_PNG_BYTES, f"{id_}: {p} > 500 KB ({p.stat().st_size} B)")

        for sc in data.get("skopy", []):
            p = cache_root / sc["plik"]
            check(p.exists(), f"{id_}: brak pliku skopu {p}")
            if p.exists():
                check(p.stat().st_size <= MAX_PNG_BYTES, f"{id_}: {p} > 500 KB ({p.stat().st_size} B)")

        zrodlo = data.get("zrodlo", {})
        check(zrodlo.get("kamera") == case["kamera"], f"{id_}: kamera={zrodlo.get('kamera')} oczekiwano {case['kamera']}")

        niepewnosc = data.get("niepewnosc", {})
        if case["kamera"] == "Fuji":
            check(zrodlo.get("lut_pomiarowy") is not None, f"{id_}: lut_pomiarowy powinien byc ustawiony dla Fuji")
            check(niepewnosc.get("pomiar_bez_lut") is False, f"{id_}: niepewnosc.pomiar_bez_lut powinno byc false dla Fuji")
        else:
            check(zrodlo.get("lut_pomiarowy") is None, f"{id_}: lut_pomiarowy powinien byc null dla {case['kamera']}")

    if failures:
        print(f"SMOKE TEST: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("SMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
