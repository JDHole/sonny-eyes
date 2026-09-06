"""Test dymny i18n strony przegladu i wykresu przebiegu (bramka Z1). Dziala
jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_review_lang.py

Kopiuje 2 prawdziwe raporty (i ich PNG-i - strona review laduje obrazy jako
data URI z dysku) do katalogu tymczasowego w strukturze `--out`, potem
generuje `review --lang en`, `review --lang pl` i `profile --lang en` na tej
kopii. Sprawdza: wersja en nie ma polskich znakow diakrytycznych (poza data
URI - a alfabet base64 fizycznie nie moze ich zawierac, wiec sam brak znakow
diakrytycznych w calym pliku juz to gwarantuje), wersja pl ma sekcje
"Jak czytac liczby", i `profile --lang en` faktycznie rysuje PNG.

Uzywa config.toml autora (jak tests/test_smoke.py) do znalezienia prawdziwych
raportow - u siebie zacznij od tests/test_config.py i tests/test_cli.py."""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import re
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_profile, cmd_review  # noqa: E402
from eyes.config import load_config  # noqa: E402

PROJECT = "Canarian Tweety EP03"
IDS = ["DSCF0934", "DSCF0935"]

# Polskie znaki diakrytyczne (male i wielkie) - alfabet base64 (A-Za-z0-9+/=)
# fizycznie nie moze ich zawierac, wiec nie trzeba osobno wycinac data URI.
POLISH_CHARS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    cfg = load_config(REPO_ROOT / "config.toml")
    report_dir = cfg.reports_dir(PROJECT)
    cache_root = Path(cfg.cache_root)

    for id_ in IDS:
        src_report = report_dir / f"{id_}.json"
        if not src_report.exists():
            print(f"POMINIETO: brak raportu {src_report} (odpal na maszynie autora, patrz docstring)")
            print("TEST_REVIEW_LANG: SKIP")
            return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # --- skopiuj raporty + PNG do struktury --out (tmp/{project}/...) ---
        (tmp / PROJECT / "reports").mkdir(parents=True, exist_ok=True)
        for id_ in IDS:
            shutil.copy2(report_dir / f"{id_}.json", tmp / PROJECT / "reports" / f"{id_}.json")
            for sub in ("frames", "scopes"):
                src_dir = cache_root / PROJECT / id_ / sub
                dst_dir = tmp / PROJECT / id_ / sub
                dst_dir.mkdir(parents=True, exist_ok=True)
                for p in src_dir.glob("*.png"):
                    shutil.copy2(p, dst_dir / p.name)

        # --- review --lang en ---
        rc = cmd_review.main(["--project", PROJECT, "--out", str(tmp), "--lang", "en"])
        check(rc == 0, f"review --lang en: exit code {rc}")
        html_page = tmp / PROJECT / "_przeglad.html"
        check(html_page.exists(), f"review --lang en: brak {html_page}")
        content_en = html_page.read_text(encoding="utf-8") if html_page.exists() else ""
        # Wytnij base64 z data URI PRZED szukaniem - losowy base64 potrafi
        # przypadkiem zawierac ciag pasujacy do regexu (np. "...URKUBAiorB...")
        # i dac falszywy alarm; sam alfabet base64 (A-Za-z0-9+/=) i tak nie
        # moze zawierac polskich znakow diakrytycznych.
        bez_data_uri = re.sub(r"base64,[A-Za-z0-9+/=]+", "base64,<CUT>", content_en)

        polskie = POLISH_CHARS.findall(bez_data_uri)
        check(not polskie, f"review --lang en: znaleziono polskie znaki diakrytyczne w wersji en: {set(polskie)}")
        check("sonny-eyes" in content_en, "review --lang en: brak app_title 'sonny-eyes' w <title>/<h1>")
        check("clips measured" in content_en, "review --lang en: brak tlumaczenia licznika 'clips measured'")
        check("How to read the numbers" in content_en, "review --lang en: brak sekcji 'How to read the numbers'")
        widoczne_kuba = re.findall(r"kub[ayie]", bez_data_uri, re.IGNORECASE)
        check(not widoczne_kuba, f"review --lang en: 'Kuba'/'Kuby' w tekscie strony ({widoczne_kuba})")

        # --- review --lang pl ---
        rc = cmd_review.main(["--project", PROJECT, "--out", str(tmp), "--lang", "pl"])
        check(rc == 0, f"review --lang pl: exit code {rc}")
        content_pl = html_page.read_text(encoding="utf-8") if html_page.exists() else ""
        check("Jak czytać liczby" in content_pl, "review --lang pl: brak sekcji 'Jak czytać liczby'")
        check("Oczy Sonny'ego" in content_pl, "review --lang pl: brak app_title 'Oczy Sonny'ego'")

        # --- profile --lang en: faktycznie rysuje PNG ---
        przebieg_png = tmp / PROJECT / IDS[0] / "scopes" / f"{IDS[0]}_przebieg.png"
        size_before = przebieg_png.stat().st_size if przebieg_png.exists() else None
        rc = cmd_profile.main(["--project", PROJECT, "--out", str(tmp), "--lang", "en", "--ids", IDS[0]])
        check(rc == 0, f"profile --lang en: exit code {rc}")
        check(przebieg_png.exists(), f"profile --lang en: brak {przebieg_png}")
        if przebieg_png.exists():
            check(przebieg_png.stat().st_size > 0, "profile --lang en: PNG ma 0 bajtow")
            if size_before is not None:
                check(przebieg_png.stat().st_size != 0, "profile --lang en: PNG nie zostal nadpisany")

    if failures:
        print(f"TEST_REVIEW_LANG: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_REVIEW_LANG: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
