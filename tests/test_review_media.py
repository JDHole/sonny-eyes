"""Test strony przegladu dla zdjec i audio (bez materialu, bez pytest):

    .venv/Scripts/python.exe tests/test_review_media.py

Strona przegladu brala obrazek karty zawsze z {id}_najostrzejsza.png (klatka
wideo), wiec karty zdjec ({id}_podglad.jpg z cmd_photo) i audio
({id}_fala.png z cmd_asset) wychodzily bez obrazka. Test sklada w katalogu
tymczasowym (struktura --out) trzy syntetyczne raporty - wideo, zdjecie,
audio - z obrazkami pod sciezkami z ich `klatki`, generuje strone w obu
trybach (pelnym i --compact) i sprawdza, ze kazda karta ma niepusty obrazek,
a w trybie pelnym dokladnie ten plik, ktory wskazuje raport. Nie potrzebuje
ffmpeg ani prawdziwych plikow - tylko Pillow.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import re
import tempfile
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_review  # noqa: E402

PROJECT = "TestReviewMedia"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def _report(id_: str, rodzaj: str, cegla_rel: str, *, tonalnosc: dict | None) -> dict:
    """Minimalny raport w ksztalcie, ktory czyta cmd_review (pola, ktorych
    strona nie dotyka, pominiete)."""
    return {
        "wersja_metryk": "0.2",
        "id": id_,
        "projekt": PROJECT,
        "zrodlo": {"plik": f"{id_}.x", "kamera": "nieznana", "profil": None, "czas_s": None, "rodzaj": rodzaj},
        "tonalnosc": tonalnosc,
        "kolor": None if tonalnosc is None else {"sat_mean": 0.2},
        "ostrosc": None if tonalnosc is None else {"lapvar": 100.0},
        "ruch": {"klasa": [], "metoda": None},
        "klatki": [
            {"rola": "pierwsza", "plik": cegla_rel},
            {"rola": "najostrzejsza", "plik": cegla_rel},
        ],
        "skopy": [],
        "flagi_prowizoryczne": [],
    }


def _img(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = "JPEG" if path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    Image.new("RGB", size, color).save(path, fmt)


def _karty(page: str) -> dict[str, str]:
    """{id karty: src obrazka karty} ze strony."""
    out = {}
    for m in re.finditer(r'<article class="card" data-id="([^"]+)".*?<img src="([^"]*)"', page, re.S):
        out[m.group(1)] = m.group(2)
    return out


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="eyes_test_review_media_") as tmp_s:
        out = Path(tmp_s)
        reports = out / PROJECT / "reports"
        reports.mkdir(parents=True)
        ton = {"p5": 0.1, "p50": 0.5, "p99": 0.9, "clip_hi_pct": 0.0}

        przypadki = {
            # id: (rodzaj, plik obrazka wzgledem cache_root, rozmiar, kolor)
            "VID0001": ("video", f"{PROJECT}/VID0001/frames/VID0001_najostrzejsza.png", (64, 36), (200, 0, 0)),
            "DSCF0001": ("foto", f"{PROJECT}/DSCF0001/frames/DSCF0001_podglad.jpg", (60, 40), (0, 200, 0)),
            "track": ("audio", f"{PROJECT}/track/frames/track_fala.png", (160, 40), (0, 0, 200)),
        }
        for id_, (rodzaj, rel, size, color) in przypadki.items():
            _img(out / rel, size, color)
            r = _report(id_, rodzaj, rel, tonalnosc=None if rodzaj == "audio" else ton)
            (reports / f"{id_}.json").write_text(json.dumps(r), encoding="utf-8")

        # raport starszego ksztaltu bez roli "najostrzejsza" w klatki - dawna
        # sciezka wideo ma dalej dzialac
        stary = _report("VID0002", "video", "", tonalnosc=ton)
        stary["klatki"] = []
        (reports / "VID0002.json").write_text(json.dumps(stary), encoding="utf-8")
        _img(out / PROJECT / "VID0002" / "frames" / "VID0002_najostrzejsza.png", (64, 36), (90, 90, 90))

        page_path = out / PROJECT / "_przeglad.html"
        for tryb, extra in (("pelny", []), ("compact", ["--compact"])):
            rc = cmd_review.main(["--project", PROJECT, "--out", str(out), "--lang", "en", *extra])
            check(rc == 0, f"review ({tryb}): exit code {rc}")
            page = page_path.read_text(encoding="utf-8") if page_path.exists() else ""
            karty = _karty(page)
            for id_ in [*przypadki, "VID0002"]:
                src = karty.get(id_)
                check(src is not None, f"review ({tryb}): brak karty {id_}")
                check(bool(src) and src.startswith("data:image/"), f"review ({tryb}): karta {id_} bez obrazka (src={src[:40] if src else src!r})")
            if tryb == "pelny":
                for id_, (_rodzaj, rel, _s, _c) in przypadki.items():
                    oczekiwany = cmd_review.data_uri(out / rel)
                    check(karty.get(id_) == oczekiwany, f"review (pelny): karta {id_} nie pokazuje pliku z raportu ({rel})")

    if failures:
        print(f"TEST_REVIEW_MEDIA: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_REVIEW_MEDIA: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
