"""Przemial folderu (porcja D4): skanuje folder(y) rekurencyjnie po plikach z kamer i mierzy je raportem ujecia.

Uzycie (venv):
  scripts/przemial.py --project "Canarian Tweety EP03" --folder "<sciezka>" ["<sciezka2>" ...] [--force] [--no-gpu] [--limit N]
Pliki: DSCF*.MOV (Fuji), GX*/GH*/GOPR*.MP4 (GoPro). Podglady GoPro (.LRV, .THM) i wszystko inne pomijane.
Dedup po hash_4mb, klucz, pomijanie gotowych raportow: wszystko robi measure.main (ta sama sciezka co pojedynczy pomiar).
Przerwanie w dowolnym momencie jest bezpieczne: ponowne uruchomienie pomija klipy, ktore juz maja raport.
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import measure  # noqa: E402

PATTERNS = ("dscf*.mov", "gx*.mp4", "gh*.mp4", "gopr*.mp4")


def zbierz(foldery: list[str]) -> list[Path]:
    files: set[Path] = set()
    for fo in foldery:
        root = Path(fo)
        if not root.is_dir():
            print(f"UWAGA: folder nie istnieje: {root}", file=sys.stderr)
            continue
        for p in root.rglob("*"):
            if p.is_file() and any(fnmatch.fnmatch(p.name.lower(), pat) for pat in PATTERNS):
                files.add(p)
    return sorted(files, key=lambda p: str(p).replace("\\", "/"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Przemial folderu raportem ujecia (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--folder", required=True, nargs="+")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="tylko pierwsze N plikow (test porcji)")
    a = ap.parse_args(argv)

    files = zbierz(a.folder)
    if a.limit:
        files = files[: a.limit]
    t0 = time.perf_counter()
    print(f"przemial start {time.strftime('%Y-%m-%d %H:%M:%S')}: {len(files)} plikow z {len(a.folder)} folderow -> projekt \"{a.project}\"", flush=True)
    if not files:
        return 1
    argv2 = ["--project", a.project, "--files", *map(str, files)]
    if a.force:
        argv2.append("--force")
    if a.no_gpu:
        argv2.append("--no-gpu")
    rc = measure.main(argv2)
    print(f"przemial koniec {time.strftime('%Y-%m-%d %H:%M:%S')}: {(time.perf_counter() - t0) / 60:.1f} min, kod {rc}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
