"""Przemial folderu (porcja D4): skanuje folder(y) rekurencyjnie po plikach z kamer i mierzy je raportem ujecia.
Wywolywane przez `python -m eyes batch` (eyes/cli.py, w tym `--detach` -
patrz eyes/runner.py) i przez alias `scripts/przemial.py`.

Uzycie (venv):
  python -m eyes batch --project "Canarian Tweety EP03" --folder "<sciezka>" ["<sciezka2>" ...]
                        [--porcja "Dzien 7"] [--force] [--no-gpu] [--limit N] [--out X] [--config X] [--lut X]
Pliki: DSCF*.MOV (Fuji), GX*/GH*/GOPR*.MP4 (GoPro). Podglady GoPro (.LRV, .THM) i wszystko inne pomijane.
Dedup po hash_4mb, klucz, pomijanie gotowych raportow: wszystko robi cmd_measure.main (ta sama sciezka co pojedynczy pomiar).
Przerwanie w dowolnym momencie jest bezpieczne: ponowne uruchomienie pomija klipy, ktore juz maja raport.

Postep: {cache_root}/{project}/_postep.json (schema postep-przemialu/0.1), nadpisywany atomowo po KAZDYM pliku:
  projekt, porcja, foldery, status (w toku | zakonczony | zakonczony z bledami | przerwany), start, koniec, aktualizacja,
  plikow, zrobione, ok, pominiete, duplikaty, bledy, sredni_czas_s, eta_s, eta_koniec, ostatni {id, plik, status, czas_calkowity_s}.
Widget czyta ten plik zamiast pytac Sonny'ego "ile zostalo". Historia per plik: _log.jsonl.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_asset  # noqa: E402
from eyes import cmd_measure as measure  # noqa: E402
from eyes import cmd_photo  # noqa: E402
from eyes import keys as keys_mod  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402

PATTERNS = ("dscf*.mov", "gx*.mp4", "gh*.mp4", "gopr*.mp4")

# --rodzaj foto: rozszerzenia skanowane rekurencyjnie (kontrakt 2026-09-12).
PATTERNS_FOTO = ("*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff", "*.raf", "*.dng", "*.heic")
# --rodzaj assets: audio + image + video (dokladnie jak cmd_asset._kind_for_ext).
PATTERNS_ASSETS = (
    "*.wav", "*.mp3", "*.m4a", "*.flac", "*.aac",
    "*.png", "*.jpg", "*.jpeg", "*.webp", "*.svg",
    "*.mp4", "*.mov",
)
# Sufiksy stemu do POMINIECIA przy skanowaniu foto i obrazow w assetach (_IG jest
# odnotowywany przez cmd_photo.measure_photo jako warianty.ig przy pomiarze
# pliku bazowego - tu tylko wykluczany z listy PLIKOW DO ZMIERZENIA; _stock/
# _export nie maja wlasnej sekcji w kontrakcie, sa to po prostu kopie do
# pominiecia w przemiale, jak _IG).
SKIP_STEM_SUFFIXES = ("_ig", "_stock", "_export")


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


def _zbierz_wg_wzorcow(foldery: list[str], wzorce: tuple[str, ...]) -> set[Path]:
    files: set[Path] = set()
    for fo in foldery:
        root = Path(fo)
        if not root.is_dir():
            print(f"UWAGA: folder nie istnieje: {root}", file=sys.stderr)
            continue
        for p in root.rglob("*"):
            if p.is_file() and any(fnmatch.fnmatch(p.name.lower(), pat) for pat in wzorce):
                files.add(p)
    return files


def _ma_pominiety_sufiks(name: str) -> bool:
    stem, _ext = keys_mod.split_base_ext(name)
    low = stem.lower()
    return any(low.endswith(suf) for suf in SKIP_STEM_SUFFIXES)


def zbierz_foto(foldery: list[str]) -> list[Path]:
    """Jak zbierz(), ale dla zdjec: pomija warianty _IG/_stock/_export, i
    PARUJE JPG+RAF tego samego stemu w tym samym folderze - mierzony jest
    TYLKO JPG (RAF trafia do warianty.raf przy pomiarze, patrz
    cmd_photo.measure_photo), zeby nie dostac dwoch raportow (rozny wariant =
    rozny klucz w keys.py) na jedno ujecie."""
    candidates = [p for p in _zbierz_wg_wzorcow(foldery, PATTERNS_FOTO) if not _ma_pominiety_sufiks(p.name)]

    grupy: dict[tuple[str, str], list[tuple[str, Path]]] = {}
    for p in candidates:
        stem, ext = keys_mod.split_base_ext(p.name)
        klucz = (str(p.parent).lower(), stem.lower())
        grupy.setdefault(klucz, []).append((ext, p))

    wynik: list[Path] = []
    for items in grupy.values():
        jpg = next((p for e, p in items if e in ("jpg", "jpeg")), None)
        if jpg is not None:
            wynik.append(jpg)
        else:
            wynik.append(sorted((p for _e, p in items), key=lambda x: str(x).lower())[0])
    return sorted(wynik, key=lambda p: str(p).replace("\\", "/"))


def zbierz_assets(foldery: list[str]) -> list[Path]:
    """Jak zbierz(), ale dla assetow (audio+image+video mieszane w jednym
    przemiale). Warianty _IG/_stock/_export pomija TYLKO dla obrazow (png/jpg/
    webp/svg) - to kopie zdjecia bazowego. Audio i wideo z taka koncowka
    (track_stock.wav, clip_export.mp4) to samodzielne pliki i sa mierzone
    (decyzja Kuby 2026-10-20)."""
    def pomin(p: Path) -> bool:
        if not _ma_pominiety_sufiks(p.name):
            return False
        return cmd_asset._kind_for_ext(p.suffix.lower().lstrip(".")) in ("image", "svg")

    candidates = [p for p in _zbierz_wg_wzorcow(foldery, PATTERNS_ASSETS) if not pomin(p)]
    return sorted(candidates, key=lambda p: str(p).replace("\\", "/"))


def _teraz() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def zapisz_postep(path: Path, stan: dict) -> None:
    """Zapis atomowy: plik tymczasowy + os.replace, zeby czytelnik nigdy nie zobaczyl polowy JSON-a."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stan, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Przemial folderu raportem ujecia (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--folder", required=True, nargs="+")
    ap.add_argument(
        "--rodzaj", choices=["video", "foto", "assets"], default="video",
        help="co skanowac: video (domyslnie, jak dzis: DSCF*.MOV/GX*/GH*/GOPR*.MP4), "
        "foto (JPG/RAF/PNG/TIF/DNG/HEIC, parowanie JPG+RAF), assets (audio+image+video mieszane)",
    )
    ap.add_argument("--porcja", default=None, help="nazwa porcji do _postep.json (domyslnie nazwa pierwszego folderu)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="tylko pierwsze N plikow (test porcji)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--lut", default=None)
    ap.add_argument("--lang", choices=["pl", "en"], default=None, help="jezyk wykresu przebiegu; domyslnie z configu/env, inaczej en")
    ap.add_argument("--cache-root", default=None, help=argparse.SUPPRESS)  # przestarzale: alias --out
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)

    overrides = overrides_from_out(a.out or a.cache_root)
    cfg = load_config(a.config, overrides=overrides)
    postep_path = Path(cfg.cache_root) / a.project / "_postep.json"

    zbieracz = {"video": zbierz, "foto": zbierz_foto, "assets": zbierz_assets}[a.rodzaj]
    files = zbieracz(a.folder)
    if a.limit:
        files = files[: a.limit]
    t0 = time.perf_counter()
    stan = {
        "schema": "postep-przemialu/0.1",
        "projekt": a.project,
        "porcja": a.porcja or Path(a.folder[0]).name,
        "foldery": [str(Path(f)).replace("\\", "/") for f in a.folder],
        "status": "w toku",
        "start": _teraz(), "koniec": None, "aktualizacja": _teraz(),
        "plikow": len(files), "zrobione": 0, "ok": 0, "pominiete": 0, "duplikaty": 0, "bledy": 0,
        "sredni_czas_s": None, "eta_s": None, "eta_koniec": None,
        "ostatni": None,
    }
    zapisz_postep(postep_path, stan)
    print(f"przemial start {stan['start']}: {len(files)} plikow z {len(a.folder)} folderow -> projekt \"{a.project}\" (porcja: {stan['porcja']})", flush=True)
    if not files:
        stan.update(status="zakonczony", koniec=_teraz(), aktualizacja=_teraz())
        zapisz_postep(postep_path, stan)
        return 1

    czasy: list[float] = []

    def on_progress(e: dict) -> None:
        st = e.get("status")
        stan["zrobione"] = e.get("i", stan["zrobione"] + 1)
        klucz = {"ok": "ok", "pominieto": "pominiete", "duplikat": "duplikaty", "blad": "bledy"}.get(st)
        if klucz:
            stan[klucz] += 1
        if e.get("czas_calkowity_s"):
            czasy.append(float(e["czas_calkowity_s"]))
        zostalo = stan["plikow"] - stan["zrobione"]
        # duplikaty i pominiete sa ~darmowe, wiec ETA liczymy z tempa realnych pomiarow na plik NIEzrobiony
        sredni = (sum(czasy) / len(czasy)) if czasy else None
        stan["sredni_czas_s"] = round(sredni, 1) if sredni else None
        eta = (zostalo * sredni) if sredni else None
        stan["eta_s"] = round(eta) if eta is not None else None
        stan["eta_koniec"] = (dt.datetime.now().astimezone() + dt.timedelta(seconds=eta)).isoformat(timespec="seconds") if eta is not None else None
        stan["ostatni"] = {"id": e.get("id"), "plik": e.get("plik"), "status": st, "czas_calkowity_s": e.get("czas_calkowity_s")}
        stan["aktualizacja"] = _teraz()
        zapisz_postep(postep_path, stan)

    # --rodzaj foto: cmd_photo.main nie zna --no-gpu/--lut/--lang (LUT nie ma
    # zastosowania do zdjec, patrz kontrakt) - argv2 dostaje TYLKO to, co ta
    # podkomenda rozumie, inaczej argparse odmowi "unrecognized arguments".
    argv2 = ["--project", a.project, "--files", *map(str, files)]
    if a.force:
        argv2.append("--force")
    if a.out:
        argv2 += ["--out", a.out]
    if a.config:
        argv2 += ["--config", a.config]

    if a.rodzaj == "foto":
        target_main = cmd_photo.main
    else:
        if a.no_gpu:
            argv2.append("--no-gpu")
        if a.lut:
            argv2 += ["--lut", a.lut]
        if a.lang:
            argv2 += ["--lang", a.lang]
        target_main = cmd_asset.main if a.rodzaj == "assets" else measure.main

    # foto/assets: warianty (_IG, RAF, XMP) moga lezec w innym folderze niz plik
    # bazowy (typowo: JPG w folderze dnia, wersje _IG w folderze obrobionych) - podkomenda
    # zbuduje z tych korzeni JEDEN indeks na przemial (cmd_photo.zbuduj_indeks_wariantow).
    if a.rodzaj in ("foto", "assets"):
        argv2 += ["--warianty-root", *a.folder]

    try:
        rc = target_main(argv2, on_progress=on_progress)
    except KeyboardInterrupt:
        stan.update(status="przerwany", koniec=_teraz(), aktualizacja=_teraz())
        zapisz_postep(postep_path, stan)
        raise
    stan.update(status="zakonczony" if rc == 0 else "zakonczony z bledami", koniec=_teraz(), aktualizacja=_teraz(), eta_s=0)
    zapisz_postep(postep_path, stan)
    print(f"przemial koniec {stan['koniec']}: {(time.perf_counter() - t0) / 60:.1f} min, kod {rc}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
