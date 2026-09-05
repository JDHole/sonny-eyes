#!/usr/bin/env python
"""CLI: raport ujecia v0.

measure.py --project "Nazwa" --files <plik1> <plik2> ...
           [--cache-root X] [--vault X] [--no-gpu] [--force]
           [--window-start 5 --window-len 20]
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import datetime
import json
import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402

from eyes import decode as decode_mod  # noqa: E402
from eyes import keys as keys_mod  # noqa: E402
from eyes import metrics as metrics_mod  # noqa: E402
from eyes import probe as probe_mod  # noqa: E402
from eyes import report as report_mod  # noqa: E402
from eyes import scopes as scopes_mod  # noqa: E402
from eyes.config import load_config  # noqa: E402

FPS_A = 2
TARGET_WIDTH = 480
DEFAULT_WINDOW_FULL_BELOW_S = 30.0


def get_ffmpeg_version() -> str:
    try:
        r = subprocess.run(
            ["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace",
        )
        first_line = r.stdout.splitlines()[0]
        parts = first_line.split()
        return parts[2] if len(parts) > 2 else first_line
    except Exception:
        return "unknown"


def rel_to(path: Path, root: Path) -> str:
    return os.path.relpath(str(path), str(root)).replace(os.sep, "/")


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Raport ujecia v0 (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--cache-root", default=None)
    ap.add_argument("--vault", default=None)
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--window-start", type=float, default=5.0)
    ap.add_argument("--window-len", type=float, default=20.0)
    return ap.parse_args(argv)


def append_log(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_file(path: Path, *, args, cfg, hash_by_path: dict, file_paths: list[Path]) -> dict:
    """Przetwarza jeden plik. Zwraca dict do zalogowania (id, status, czas...).
    Rzuca wyjatek przy bledzie (obsluga i log bledu sa w main())."""
    cache_root = Path(cfg.cache_root)
    vault = Path(cfg.vault)
    production_root = Path(cfg.production_root)

    id_ = keys_mod.compute_id(path, file_paths, production_root)  # file_paths = lista PO dedupie
    report_dir = vault / "40_Pracownie" / "Analog Studio" / "Projekty" / args.project / "Color" / "reports"
    report_path = report_dir / f"{id_}.json"

    if report_path.exists() and not args.force:
        print(f"{id_}: raport juz istnieje, pomijam (--force wymusza ponowny pomiar)")
        return {"id": id_, "plik": path.name, "status": "pominieto", "czas_calkowity_s": None, "raport": str(report_path)}

    kamera, kamera_nieznana = keys_mod.detect_camera(path.name)
    profil = keys_mod.PROFIL_PO_KAMERZE.get(kamera)

    lut_dir = None
    lut_name = None
    lut_pomiarowy = None
    if kamera == "Fuji":
        lut_dir, lut_name = decode_mod.ensure_lut_cached(cfg.lut_fuji, cache_root)
        lut_pomiarowy = Path(cfg.lut_fuji).name

    info = probe_mod.probe(str(path))
    duration = info["duration_s"] or 0.0

    requested_end = args.window_start + args.window_len
    if duration < DEFAULT_WINDOW_FULL_BELOW_S:
        start_s, win_len = 0.0, duration
    else:
        start_s, win_len = args.window_start, args.window_len
    koniec_s = start_s + win_len
    okno_krotsze = duration < requested_end

    # Ruch (probka B) probkuje CALY klip od 0 s, niezaleznie od okna A powyzej
    # - patrz plan_probkowania_ruchu (10/5 kl/s, twardy limit 180 s materialu).
    fps_b, dlugosc_b, obciete_s = metrics_mod.plan_probkowania_ruchu(duration)

    t_start_total = time.perf_counter()

    dec_a = decode_mod.decode_frames(
        str(path), start_s, win_len, fps=FPS_A, orig_w=info["w"], orig_h=info["h"],
        target_w=TARGET_WIDTH, lut_dir=lut_dir, lut_name=lut_name,
        grayscale=False, use_gpu=not args.no_gpu,
    )
    # bez LUT - ruch nie potrzebuje LUT (kolor/tonalnosc nie sa tu liczone).
    dec_b = decode_mod.decode_frames(
        str(path), 0.0, dlugosc_b, fps=fps_b, orig_w=info["w"], orig_h=info["h"],
        target_w=TARGET_WIDTH, lut_dir=None, lut_name=None,
        grayscale=True, use_gpu=not args.no_gpu,
    )

    t_decode_total = dec_a["decode_time_s"] + dec_b["decode_time_s"]
    gpu_used = bool(dec_a["gpu_used"] and dec_b["gpu_used"])
    gpu_fallback = bool(dec_a["gpu_fallback"] or dec_b["gpu_fallback"])

    frames_a = dec_a["frames"]
    frames_b = dec_b["frames"]

    tonalnosc = metrics_mod.compute_tonalnosc(frames_a)
    kolor = metrics_mod.compute_kolor(frames_a)
    ostrosc, idx_sharp = metrics_mod.compute_ostrosc(frames_a)
    szum = metrics_mod.compute_szum(frames_a[idx_sharp])
    ruch = metrics_mod.compute_ruch(frames_b, fps_b=fps_b, target_width=dec_b["width"])
    ruch["obcieto_s"] = obciete_s
    plynnosc = metrics_mod.compute_plynnosc(frames_b, info["fps"], info["fps_avg"])
    montaz = metrics_mod.compute_montaz(duration)
    flagi = metrics_mod.compute_flagi(tonalnosc, ostrosc, ruch)

    id_cache_dir = cache_root / args.project / id_
    frames_dir = id_cache_dir / "frames"
    scopes_dir = id_cache_dir / "scopes"

    pierwsza_path = frames_dir / f"{id_}_pierwsza.png"
    najostrzejsza_path = frames_dir / f"{id_}_najostrzejsza.png"
    scopes_mod.save_thumbnail(frames_a[0], pierwsza_path)
    scopes_mod.save_thumbnail(frames_a[idx_sharp], najostrzejsza_path)

    t_sharp = start_s + idx_sharp / FPS_A
    waveform_path = scopes_dir / f"{id_}_waveform.png"
    vectorscope_path = scopes_dir / f"{id_}_vectorscope.png"
    scopes_mod.render_scope(str(path), t_sharp, "waveform", waveform_path, lut_dir=lut_dir, lut_name=lut_name)
    scopes_mod.render_scope(str(path), t_sharp, "vectorscope", vectorscope_path, lut_dir=lut_dir, lut_name=lut_name)

    klatki = [
        {"rola": "pierwsza", "t_s": round(start_s, 3), "plik": rel_to(pierwsza_path, cache_root)},
        {"rola": "najostrzejsza", "t_s": round(t_sharp, 3), "plik": rel_to(najostrzejsza_path, cache_root)},
    ]
    skopy = [
        {"typ": "waveform", "t_s": round(t_sharp, 3), "plik": rel_to(waveform_path, cache_root)},
        {"typ": "vectorscope", "t_s": round(t_sharp, 3), "plik": rel_to(vectorscope_path, cache_root)},
    ]

    stat = path.stat()
    zrodlo = {
        "plik": path.name,
        "sciezka_rel": rel_to(path, production_root),
        "hash_4mb": hash_by_path[path],
        "rozmiar_b": stat.st_size,
        "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "kamera": kamera,
        "profil": profil,
        "lut_pomiarowy": lut_pomiarowy,
        "czas_s": duration,
    }
    stream = {
        "codec": info["codec"], "w": info["w"], "h": info["h"],
        "fps": info["fps"], "fps_avg": info["fps_avg"], "pix_fmt": info["pix_fmt"],
        "range": info["range"], "transfer": info["transfer"], "primaries": info["primaries"],
        "nb_frames": info["nb_frames"],
    }
    okno = {
        "start_s": start_s, "koniec_s": koniec_s,
        "fps_probki_a": FPS_A, "fps_probki_b": fps_b, "szerokosc_px": TARGET_WIDTH,
        "liczba_klatek_a": int(frames_a.shape[0]), "liczba_klatek_b": int(frames_b.shape[0]),
    }
    niepewnosc = {
        "pomiar_bez_lut": bool(kamera == "Fuji" and lut_name is None),
        "kamera_nieznana": bool(kamera_nieznana),
        "gpu_fallback_cpu": gpu_fallback,
        "okno_krotsze_niz_zadane": bool(okno_krotsze),
    }

    t_total = time.perf_counter() - t_start_total

    pomiar = {
        "data": datetime.datetime.now().astimezone().isoformat(),
        "czas_dekodowania_s": t_decode_total,
        "czas_calkowity_s": t_total,
        "gpu": gpu_used,
        "ffmpeg": get_ffmpeg_version(),
        "opencv": cv2.__version__,
        "host": "laptop",
    }

    report = report_mod.build_report(
        id_=id_, projekt=args.project, zrodlo=zrodlo, stream=stream, okno_pomiaru=okno,
        tonalnosc=tonalnosc, kolor=kolor, ostrosc=ostrosc, szum=szum, ruch=ruch,
        plynnosc=plynnosc, montaz=montaz, klatki=klatki, skopy=skopy,
        flagi=flagi, progi=metrics_mod.PROGI_PROWIZORYCZNE, niepewnosc=niepewnosc, pomiar=pomiar,
    )
    report_mod.write_report(report, report_path)

    gpu_txt = "tak" if gpu_used else "nie"
    print(
        f"{id_}: kamera={kamera} gpu={gpu_txt} "
        f"dekodowanie={t_decode_total:.2f}s calkowity={t_total:.2f}s raport={report_path}"
    )
    return {"id": id_, "plik": path.name, "status": "ok", "czas_calkowity_s": round(t_total, 3), "raport": str(report_path)}


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config(
        REPO_ROOT / "config.toml",
        overrides={"vault": args.vault, "cache_root": args.cache_root},
    )
    cache_root = Path(cfg.cache_root)
    file_paths = [Path(f).resolve() if Path(f).exists() else Path(f) for f in args.files]

    hash_by_path = {p: keys_mod.hash_4mb(p) for p in file_paths}
    dup_map = keys_mod.find_duplicate_hashes(file_paths)
    # kolizje id liczymy na liscie PO dedupie: identyczna tresc to jedno ujecie, nie kolizja (kontrakt z Dexterem)
    unique_paths = [p for p in file_paths if p not in dup_map]
    production_root = Path(cfg.production_root)

    project_cache = cache_root / args.project
    log_path = project_cache / "_log.jsonl"

    any_failed = False

    for path in file_paths:
        if path in dup_map:
            original = dup_map[path]
            print(f"{path.name}: POMINIETO, identyczny hash_4mb jak {original.name} (duplikat)")
            append_log(log_path, {
                "id": keys_mod.compute_id(original, unique_paths, production_root),
                "plik": path.name,
                "sciezka_rel": str(path).replace("\\", "/"),
                "status": "duplikat",
                "duplikat_of": str(original).replace("\\", "/"),
                "hash_4mb": hash_by_path[path],
                "czas_calkowity_s": None,
                "data": datetime.datetime.now().astimezone().isoformat(),
                "wersja_metryk": "0.2",
            })
            continue
        try:
            result = process_file(path, args=args, cfg=cfg, hash_by_path=hash_by_path, file_paths=unique_paths)
            append_log(log_path, {
                "id": result["id"],
                "plik": result["plik"],
                "status": result["status"],
                "czas_calkowity_s": result["czas_calkowity_s"],
                "data": datetime.datetime.now().astimezone().isoformat(),
                "wersja_metryk": "0.2",
            })
        except Exception as e:  # noqa: BLE001
            any_failed = True
            print(f"{path.name}: BLAD {e}", file=sys.stderr)
            append_log(log_path, {
                "id": keys_mod.compute_id(path, unique_paths, production_root),
                "plik": path.name,
                "status": "blad",
                "czas_calkowity_s": None,
                "error": str(e),
                "data": datetime.datetime.now().astimezone().isoformat(),
                "wersja_metryk": "0.2",
            })
            continue

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
