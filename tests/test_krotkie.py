"""Test bardzo krotkich klipow (bez materialu, bez pytest):

    .venv/Scripts/python.exe tests/test_krotkie.py

Przypadkowe nagrania GoPro po 0,2-0,3 s (4-7 klatek) wywalaly pomiar
surowym bledem numpy (pusty kwantyl w oknie A, za krotka seria dla sredniej
ruchomej ruchu). Teraz taki klip jest pomijany z powodem "za_krotki", bez
raportu i bez bledu przemialu. Test generuje ffmpegiem (lavfi testsrc2) dwa
klipy w katalogu tymczasowym: 0,3 s (ma byc pominiety) i 0,6 s (najkrotszy,
ktory sie mierzy przy 25 kl/s) i puszcza na nich przemial `eyes batch`.
Potrzebny tylko ffmpeg.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_batch  # noqa: E402

PROJECT = "TestKrotkie"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def klip(path: Path, sekundy: float) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25",
         "-t", str(sekundy), "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)],
        check=True, stdin=subprocess.DEVNULL,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="eyes_test_krotkie_") as tmp_s:
        tmp = Path(tmp_s)
        folder = tmp / "klipy"
        folder.mkdir()
        klip(folder / "GX010001.MP4", 0.3)
        klip(folder / "GX010002.MP4", 0.6)
        out = tmp / "out"

        rc = cmd_batch.main(["--project", PROJECT, "--folder", str(folder), "--out", str(out), "--no-gpu"])
        check(rc == 0, f"batch: kod {rc}, oczekiwano 0 (krotki klip to pominiecie, nie blad)")

        reports = out / PROJECT / "reports"
        check(not (reports / "GX010001.json").exists(), "GX010001 (0,3 s): powstal raport, a mial byc pominiety")
        check((reports / "GX010002.json").exists(), "GX010002 (0,6 s): brak raportu, a ma sie mierzyc")

        log = out / PROJECT / "_log.jsonl"
        wpisy = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        krotki = [w for w in wpisy if w.get("plik") == "GX010001.MP4"]
        check(len(krotki) == 1, f"_log.jsonl: wpisow dla GX010001 {len(krotki)}, oczekiwano 1")
        if krotki:
            check(krotki[0].get("status") == "pominieto", f"GX010001: status={krotki[0].get('status')!r}, oczekiwano 'pominieto'")
            check(krotki[0].get("powod") == "za_krotki", f"GX010001: powod={krotki[0].get('powod')!r}, oczekiwano 'za_krotki'")

        postep = json.loads((out / PROJECT / "_postep.json").read_text(encoding="utf-8"))
        check(postep.get("status") == "zakonczony", f"_postep.json status={postep.get('status')!r}")
        check(postep.get("ok") == 1 and postep.get("pominiete") == 1 and postep.get("bledy") == 0,
              f"_postep.json ok={postep.get('ok')} pominiete={postep.get('pominiete')} bledy={postep.get('bledy')}, oczekiwano 1/1/0")

    if failures:
        print(f"TEST_KROTKIE: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_KROTKIE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
