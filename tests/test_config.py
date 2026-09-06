"""Test dymny configu (bramka Z1). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_config.py

Sprawdza: domyslne wartosci bez zadnego pliku, szablon reports_root z
{project}, stare klucze (vault/production_root/lut_fuji) -> czytelny
ConfigError (nie traceback), i nadpisania przez env EYES_OUT/EYES_CONFIG.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes.config import Config, ConfigError, load_config  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- 1. domyslne, calkowity brak pliku configu ---
        nieistniejacy = tmp / "brak_config.toml"
        cfg = load_config(nieistniejacy)
        check(isinstance(cfg, Config), "load_config bez pliku nie zwrocilo Config")
        check(cfg.out_root == "./eyes-out", f"domyslny out_root={cfg.out_root!r}, oczekiwano './eyes-out'")
        check(cfg.cache_root == cfg.out_root, f"domyslny cache_root={cfg.cache_root!r} powinien = out_root")
        check(cfg.lut == {}, f"domyslne lut={cfg.lut!r}, oczekiwano pustego dict")
        check("{project}" in cfg.reports_root, f"domyslny reports_root={cfg.reports_root!r} bez {{project}}")

        # --- 2. szablon {project} w reports_root faktycznie sie formatuje ---
        rd = cfg.reports_dir("Moj Projekt")
        check("Moj Projekt" in str(rd), f"reports_dir nie podstawilo nazwy projektu: {rd}")
        check(cfg.color_dir("Moj Projekt") == rd.parent, "color_dir powinien byc rodzicem reports_dir")

        # --- 3. plik configu z nowymi kluczami, override reports_root wprost ---
        cfg_path = tmp / "config.toml"
        cfg_path.write_text(
            'out_root = "D:/gdzies/out"\n'
            'reports_root = "D:/inne/{project}/raporty"\n'
            "[lut]\n"
            'fuji = "D:/luty/flog.cube"\n',
            encoding="utf-8",
        )
        cfg2 = load_config(cfg_path)
        check(cfg2.out_root == "D:/gdzies/out", f"out_root z pliku={cfg2.out_root!r}")
        check(cfg2.cache_root == "D:/gdzies/out", f"cache_root powinien domyslnie = out_root, jest {cfg2.cache_root!r}")
        check(cfg2.reports_dir("P") == Path("D:/inne/P/raporty"), f"reports_dir(P)={cfg2.reports_dir('P')}")
        check(cfg2.lut.get("fuji") == "D:/luty/flog.cube", f"lut.fuji={cfg2.lut.get('fuji')!r}")

        # --- 4. stare klucze -> czytelny ConfigError, nie traceback ---
        for zly_klucz, wartosc in (("vault", "X"), ("production_root", "Y"), ("lut_fuji", "Z")):
            old_path = tmp / f"stary_{zly_klucz}.toml"
            old_path.write_text(f'{zly_klucz} = "{wartosc}"\n', encoding="utf-8")
            try:
                load_config(old_path)
                check(False, f"load_config z kluczem '{zly_klucz}' powinno rzucic ConfigError")
            except ConfigError as e:
                check(zly_klucz in str(e), f"ConfigError dla '{zly_klucz}' nie wspomina klucza: {e}")
            except Exception as e:  # noqa: BLE001
                check(False, f"load_config z kluczem '{zly_klucz}' rzucilo {type(e).__name__} zamiast ConfigError: {e}")

        # --- 5. nadpisania: CLI (overrides) > env > plik > domyslne ---
        os.environ["EYES_OUT"] = str(tmp / "z_env")
        try:
            cfg3 = load_config(nieistniejacy)  # brak pliku, samo env
            check(cfg3.out_root == str(tmp / "z_env"), f"EYES_OUT nie nadpisalo out_root: {cfg3.out_root!r}")
            check(cfg3.cache_root == cfg3.out_root, "cache_root powinien podazac za out_root z env, gdy nie ustawiony osobno")

            cfg4 = load_config(nieistniejacy, overrides={"out_root": str(tmp / "z_cli")})
            check(cfg4.out_root == str(tmp / "z_cli"), f"CLI override nie wygral z env: {cfg4.out_root!r}")
        finally:
            del os.environ["EYES_OUT"]

        # EYES_CONFIG wskazuje na plik z nowymi kluczami
        os.environ["EYES_CONFIG"] = str(cfg_path)
        try:
            cfg5 = load_config()
            check(cfg5.out_root == "D:/gdzies/out", f"EYES_CONFIG nie zadzialalo: {cfg5.out_root!r}")
        finally:
            del os.environ["EYES_CONFIG"]

        # EYES_CONFIG na nieistniejacy plik = brak configu, NIE blad
        os.environ["EYES_CONFIG"] = str(tmp / "nie_ma_takiego.toml")
        try:
            cfg6 = load_config()
            check(cfg6.out_root == "./eyes-out", f"EYES_CONFIG na brakujacy plik powinno dac domyslne, jest {cfg6.out_root!r}")
        finally:
            del os.environ["EYES_CONFIG"]

    if failures:
        print(f"TEST_CONFIG: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_CONFIG: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
