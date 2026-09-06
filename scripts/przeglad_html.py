"""Alias (zgodnosc wsteczna): logika przeniesiona do eyes/cmd_review.py,
wywolywana tez jako `python -m eyes review`. Ten skrypt istnieje wylacznie
dla zapisanych starych komend - parsuje te same argumenty i woła te sama
funkcje `main()`.

Uwaga zgodnosciowa: dawne `--out sciezka.html` (kopia strony do publikacji)
zostalo w nowym CLI przemianowane na `--out-file` (bo `--out` jest teraz
wspolna opcja "folder wyjsciowy" we wszystkich podkomendach) - ten alias
tlumaczy stare `--out` na `--out-file` automatycznie, wiec zapisane komendy
dzialaja bez zmian.

przeglad_html.py --project "Canarian Tweety EP03" [--out sciezka.html]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eyes.cmd_review import main  # noqa: E402


def _translate_legacy_out(argv: list[str]) -> list[str]:
    out = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            out.append("--out-file")
        else:
            out.append(a)
        i += 1
    return out


if __name__ == "__main__":
    sys.exit(main(_translate_legacy_out(sys.argv[1:])))
