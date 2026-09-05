#!/usr/bin/env python
"""CLI: rysuje obrazki 'przebieg ujecia' z ISTNIEJACYCH raportow (bez pomiaru).

przebieg.py --project "Nazwa" [--ids ID1 ID2 ...]

Dla kazdego wskazanego raportu (albo wszystkich *.json w projekcie, gdy brak
--ids): jesli brakuje w nim tonalnosc.profil (raport sprzed tej funkcji) -
pomija z komunikatem "brak profilu, zmierz z --force". W przeciwnym razie
rysuje {id}_przebieg.png (eyes/przebieg.py:render_przebieg) i - jesli w
raporcie nie ma jeszcze wpisu skopy typu "przebieg" - dopisuje go i
zapisuje raport z powrotem (eyes/report.py:write_report, bez zmiany innych
pol).
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import przebieg as przebieg_mod  # noqa: E402
from eyes import report as report_mod  # noqa: E402
from eyes.config import load_config  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Obrazki 'przebieg ujecia' z istniejacych raportow (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--ids", nargs="+", default=None)
    ap.add_argument("--cache-root", default=None)
    ap.add_argument("--vault", default=None)
    return ap.parse_args(argv)


def rel_to(path: Path, root: Path) -> str:
    return os.path.relpath(str(path), str(root)).replace(os.sep, "/")


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config(
        REPO_ROOT / "config.toml",
        overrides={"vault": args.vault, "cache_root": args.cache_root},
    )
    cache_root = Path(cfg.cache_root)
    vault = Path(cfg.vault)
    report_dir = vault / "40_Pracownie" / "Analog Studio" / "Projekty" / args.project / "Color" / "reports"

    if args.ids:
        report_paths = [report_dir / f"{i}.json" for i in args.ids]
    else:
        report_paths = sorted(report_dir.glob("*.json"))

    narysowano = 0
    pominieto = 0

    for report_path in report_paths:
        id_ = report_path.stem
        if not report_path.exists():
            print(f"{id_}: brak raportu {report_path}")
            pominieto += 1
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))

        if not (report.get("tonalnosc") or {}).get("profil"):
            print(f"{id_}: brak profilu, zmierz z --force")
            pominieto += 1
            continue

        out_path = cache_root / args.project / id_ / "scopes" / f"{id_}_przebieg.png"
        wynik = przebieg_mod.render_przebieg(report, out_path)

        if wynik is None:
            print(f"{id_}: brak profilu, zmierz z --force")
            pominieto += 1
            continue

        skopy = report.setdefault("skopy", [])
        ma_wpis = any(s.get("typ") == "przebieg" for s in skopy)
        if not ma_wpis:
            skopy.append({"typ": "przebieg", "t_s": None, "plik": rel_to(wynik, cache_root)})
            report_mod.write_report(report, report_path)

        print(f"{id_}: narysowano {wynik}")
        narysowano += 1

    print(f"\nRazem: narysowano {narysowano}, pominieto {pominieto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
