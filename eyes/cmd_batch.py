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

from eyes import cmd_measure as measure  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402

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

    files = zbierz(a.folder)
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

    argv2 = ["--project", a.project, "--files", *map(str, files)]
    if a.force:
        argv2.append("--force")
    if a.no_gpu:
        argv2.append("--no-gpu")
    if a.out:
        argv2 += ["--out", a.out]
    if a.config:
        argv2 += ["--config", a.config]
    if a.lut:
        argv2 += ["--lut", a.lut]
    if a.lang:
        argv2 += ["--lang", a.lang]
    try:
        rc = measure.main(argv2, on_progress=on_progress)
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
