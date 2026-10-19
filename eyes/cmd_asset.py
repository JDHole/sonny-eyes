"""Logika CLI: raport assetu - audio, image (foto bez wymogu EXIF) albo video
(jak dzis). Ten sam szkielet raportu co klipy/zdjecia - patrz kontrakt sesji
"raport ujecia dla ZDJEC i ASSETOW" (wersja_metryk "0.2", 2026-09-12).
Wywolywane przez `python -m eyes asset` (eyes/cli.py) i przez
eyes/cmd_batch.py (--rodzaj assets).

asset --project "Nazwa" --files <plik1> <plik2> ...
      [--out X] [--config X] [--force] [--no-gpu] [--lut X]
      [--window-start 5 --window-len 20]

Dyspozytor po rozszerzeniu: wav/mp3/m4a/flac/aac -> audio (measure_audio);
png/jpg/jpeg/webp -> image (eyes.cmd_photo.measure_photo, rodzaj="image");
svg -> pominiete (brak dekodera, bez pip install); mp4/mov -> video (dokladnie
eyes.cmd_measure.process_file, bez zmian zachowania).

Audio: ebur128 (lufs_i/lra/true_peak_dbtp), silencedetect (cisza na
poczatku/koncu), astats (szczyt_rms_db = Peak level dB - RMS level dB,
"Overall" sekcja) - wszystko z stderr ffmpeg (bez -f null nic by sie nie
policzylo, ale zaden plik nie jest zapisywany). Fala: `showwavespic`.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import datetime
import platform
import re
import subprocess
import sys as _sys  # noqa: F401 (zachowane dla czytelnosci importow ponizej)
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_measure as measure_mod  # noqa: E402
from eyes import cmd_photo as photo_mod  # noqa: E402
from eyes import keys as keys_mod  # noqa: E402
from eyes import probe as probe_mod  # noqa: E402
from eyes import report as report_mod  # noqa: E402
from eyes import scopes as scopes_mod  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402

AUDIO_EXTS = ("wav", "mp3", "m4a", "flac", "aac")
IMAGE_EXTS = ("png", "jpg", "jpeg", "webp")
VIDEO_EXTS = ("mp4", "mov")

# Progi audio - PROWIZORYCZNE, wprost z kontraktu (nie kalibrowane osobno,
# to sa wartosci-litery kontraktu, nie robocze zgadywanki jak PROGI_FOTO.sigma_szum_max).
PROGI_AUDIO = {
    "cicho_lufs_max": -30.0,
    "glosno_dbtp_min": -1.0,
    "klip_dbtp_min": 0.0,
    "cisza_start_s_min": 1.0,
    "cisza_koniec_s_min": 2.0,
}

_RE_EBUR_I = re.compile(r"I:\s*(-?\d+\.?\d*)\s*LUFS")
_RE_EBUR_LRA = re.compile(r"LRA:\s*(-?\d+\.?\d*)\s*LU\b")
_RE_EBUR_PEAK = re.compile(r"Peak:\s*(-?\d+\.?\d*)\s*dBFS")
_RE_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_RE_SILENCE_END = re.compile(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)")
_RE_PEAK_DB = re.compile(r"Peak level dB:\s*(-?[\d.]+|-inf)")
_RE_RMS_DB = re.compile(r"RMS level dB:\s*(-?[\d.]+|-inf)")


def _kind_for_ext(ext: str) -> str | None:
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    if ext == "svg":
        return "svg"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def _ffmpeg_stderr_text(af: str, input_path: str) -> str:
    cmd = [scopes_mod.FFMPEG, "-hide_banner", "-nostats", "-i", str(input_path), "-af", af, "-f", "null", "-"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        # bez tego plik, ktorego ffmpeg nie zdekoduje, dostalby raport "ok"
        # z samymi nullami w audio zamiast wpisu "blad" w _log.jsonl
        raise RuntimeError(f"ffmpeg -af {af} nie powiodl sie dla {input_path}: {stderr[-500:]}")
    return stderr


def _parse_ebur128(stderr: str) -> dict:
    """Parsuje TYLKO sekcje 'Summary:' (linie 'na biezaco' maja te same
    etykiety I:/LRA:/Peak: z innymi wartosciami - branie pierwszego
    dopasowania w calym stderr lapaloby wartosc z pierwszej ramki, nie
    podsumowanie calego pliku)."""
    idx = stderr.find("Summary:")
    section = stderr[idx:] if idx != -1 else stderr

    def grab(pattern: re.Pattern) -> float | None:
        m = pattern.search(section)
        return float(m.group(1)) if m else None

    return {
        "lufs_i": grab(_RE_EBUR_I),
        "lra": grab(_RE_EBUR_LRA),
        "true_peak_dbtp": grab(_RE_EBUR_PEAK),
    }


def _parse_silence(stderr: str, duration_s: float) -> tuple[float, float]:
    """cisza_start_s/cisza_koniec_s wg kontraktu: pierwszy/ostatni odcinek
    ciszy stykajacy sie z poczatkiem/koncem pliku, inaczej 0. Tolerancja 0.05 s
    na start (silencedetect rzadko trafia dokladnie w 0.0) i 0.15 s na koniec
    (ostatni silence_end vs dlugosc z ffprobe - drobne rozjazdy zaokraglen)."""
    starts = [float(x) for x in _RE_SILENCE_START.findall(stderr)]
    ends = [(float(e), float(d)) for e, d in _RE_SILENCE_END.findall(stderr)]

    cisza_start_s = 0.0
    if starts and abs(starts[0]) < 0.05 and ends:
        cisza_start_s = ends[0][1]

    cisza_koniec_s = 0.0
    if len(starts) > len(ends) and starts:
        # ostatni silence_start bez pary silence_end = cisza trwa do EOF
        cisza_koniec_s = max(0.0, duration_s - starts[-1])
    elif ends:
        last_end, last_dur = ends[-1]
        if abs(last_end - duration_s) < 0.15:
            cisza_koniec_s = last_dur

    return cisza_start_s, cisza_koniec_s


def _parse_astats(stderr: str) -> tuple[float | None, float | None]:
    def last_val(pattern: re.Pattern) -> float | None:
        vals = pattern.findall(stderr)
        if not vals:
            return None
        v = vals[-1]
        if v == "-inf":
            return None
        try:
            return float(v)
        except ValueError:
            return None

    return last_val(_RE_PEAK_DB), last_val(_RE_RMS_DB)


def compute_flagi_audio(audio: dict, progi: dict = PROGI_AUDIO) -> list[str]:
    flagi = []
    lufs = audio.get("lufs_i")
    if lufs is not None and lufs < progi["cicho_lufs_max"]:
        flagi.append("cicho")
    tp = audio.get("true_peak_dbtp")
    if tp is not None and tp > progi["glosno_dbtp_min"]:
        flagi.append("glosno")
    if tp is not None and tp > progi["klip_dbtp_min"]:
        flagi.append("klip")
    if (audio.get("cisza_start_s") or 0.0) > progi["cisza_start_s_min"]:
        flagi.append("cisza_start")
    if (audio.get("cisza_koniec_s") or 0.0) > progi["cisza_koniec_s_min"]:
        flagi.append("cisza_koniec")
    return flagi


def measure_audio(
    path: Path, *, project: str, cfg, force: bool = False,
    hash_by_path: dict, file_paths: list[Path],
) -> dict:
    """Mierzy jeden plik audio. Zwraca dict do zalogowania - jak
    cmd_measure.process_file / cmd_photo.measure_photo."""
    cache_root = Path(cfg.cache_root)
    id_ = keys_mod.compute_id(path, file_paths)
    report_dir = cfg.reports_dir(project)
    report_path = report_dir / f"{id_}.json"

    if report_path.exists() and not force:
        print(f"{id_}: raport juz istnieje, pomijam (--force wymusza ponowny pomiar)")
        return {"id": id_, "plik": path.name, "status": "pominieto", "czas_calkowity_s": None, "raport": str(report_path)}

    t0 = time.perf_counter()

    info = probe_mod.probe_audio(str(path))
    duration_s = info["duration_s"] or 0.0

    ebur = _parse_ebur128(_ffmpeg_stderr_text("ebur128=peak=true", str(path)))
    cisza_start_s, cisza_koniec_s = _parse_silence(
        _ffmpeg_stderr_text("silencedetect=n=-50dB:d=0.3", str(path)), duration_s,
    )
    peak_db, rms_db = _parse_astats(_ffmpeg_stderr_text("astats", str(path)))
    szczyt_rms_db = (peak_db - rms_db) if (peak_db is not None and rms_db is not None) else None

    audio = {
        "czas_s": duration_s,
        "sample_rate": info["sample_rate"],
        "channels": info["channels"],
        "lufs_i": ebur["lufs_i"],
        "lra": ebur["lra"],
        "true_peak_dbtp": ebur["true_peak_dbtp"],
        "cisza_start_s": cisza_start_s,
        "cisza_koniec_s": cisza_koniec_s,
        "szczyt_rms_db": szczyt_rms_db,
    }

    id_cache_dir = cache_root / project / id_
    frames_dir = id_cache_dir / "frames"
    fala_path = frames_dir / f"{id_}_fala.png"
    kafel_path = frames_dir / f"{id_}_kafel.png"
    scopes_mod.render_wave(str(path), fala_path, size="1600x400")
    scopes_mod.render_wave(str(path), kafel_path, size="640x160")

    def rel(p: Path) -> str:
        return measure_mod.rel_to(p, cache_root)

    klatki = [
        {"rola": "pierwsza", "plik": rel(fala_path)},
        {"rola": "najostrzejsza", "plik": rel(fala_path)},
        {"rola": "kafel", "plik": rel(kafel_path)},
    ]
    skopy: list = []

    flagi = compute_flagi_audio(audio)

    stat = path.stat()
    zrodlo = {
        "plik": path.name,
        "sciezka_rel": str(path.resolve()).replace("\\", "/"),
        "hash_4mb": hash_by_path[path],
        "rozmiar_b": stat.st_size,
        "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "kamera": "nieznana",
        "profil": None,
        "lut_pomiarowy": None,
        "czas_s": duration_s,
        "rodzaj": "audio",
        "plik_pomiaru": str(path.resolve()).replace("\\", "/"),
    }
    stream = {
        "codec": info["codec"], "w": None, "h": None, "fps": None, "fps_avg": None,
        "pix_fmt": None, "range": None, "transfer": None, "primaries": None, "nb_frames": None,
        "sample_rate": info["sample_rate"], "channels": info["channels"], "bits": info["bits"], "czas_s": duration_s,
    }
    okno_pomiaru = {"tryb": "audio"}
    ruch = {"klasa": [], "metoda": None}
    plynnosc: dict = {}
    montaz = {"segmenty": []}
    niepewnosc = {
        "pomiar_bez_lut": False,
        "kamera_nieznana": True,
        "gpu_fallback_cpu": False,
        "okno_krotsze_niz_zadane": False,
    }

    t_total = time.perf_counter() - t0
    pomiar = {
        "data": datetime.datetime.now().astimezone().isoformat(),
        "czas_dekodowania_s": t_total,
        "czas_calkowity_s": t_total,
        "gpu": False,
        "ffmpeg": measure_mod.get_ffmpeg_version(),
        "opencv": __import__("cv2").__version__,
        "host": platform.node(),
    }

    report = report_mod.build_report(
        id_=id_, projekt=project, zrodlo=zrodlo, stream=stream, okno_pomiaru=okno_pomiaru,
        tonalnosc=None, kolor=None, ostrosc=None, szum=None, ruch=ruch,
        plynnosc=plynnosc, montaz=montaz, klatki=klatki, skopy=skopy,
        flagi=flagi, progi=PROGI_AUDIO, niepewnosc=niepewnosc, pomiar=pomiar,
        audio=audio,
    )
    report_mod.write_report(report, report_path)

    print(f"{id_}: rodzaj=audio lufs_i={audio['lufs_i']} calkowity={t_total:.2f}s raport={report_path}")
    return {"id": id_, "plik": path.name, "status": "ok", "czas_calkowity_s": round(t_total, 3), "raport": str(report_path)}


def measure_asset(
    path: Path, *, project: str, cfg, force: bool, hash_by_path: dict,
    file_paths: list[Path], video_args: argparse.Namespace, lut_override: str | None,
    variant_index=None,
) -> dict:
    """Dyspozytor po rozszerzeniu - jedno wejscie dla batch (--rodzaj assets)
    i `eyes asset`. `video_args`/`lut_override`: przekazywane wprost do
    cmd_measure.process_file dla plikow wideo (zachowanie identyczne z
    `eyes measure`/`eyes batch --rodzaj video`)."""
    ext = path.suffix.lower().lstrip(".")
    kind = _kind_for_ext(ext)

    if kind == "audio":
        return measure_audio(path, project=project, cfg=cfg, force=force, hash_by_path=hash_by_path, file_paths=file_paths)
    if kind == "image":
        return photo_mod.measure_photo(
            path, project=project, cfg=cfg, force=force,
            hash_by_path=hash_by_path, file_paths=file_paths, rodzaj="image",
            variant_index=variant_index,
        )
    if kind == "svg":
        id_ = keys_mod.compute_id(path, file_paths)
        print(f"{id_}: pominieto, brak dekodera dla .svg")
        return {"id": id_, "plik": path.name, "status": "pominieto", "powod": "brak_dekodera", "czas_calkowity_s": None, "raport": None}
    if kind == "video":
        return measure_mod.process_file(
            path, args=video_args, cfg=cfg, hash_by_path=hash_by_path,
            file_paths=file_paths, lut_override=lut_override,
        )
    raise RuntimeError(f"nieobslugiwane rozszerzenie w assets: .{ext} ({path})")


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Raport assetu - audio/image/video (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--lut", default=None, help="tylko dla plikow wideo w tej liscie")
    ap.add_argument("--no-gpu", action="store_true", help="tylko dla plikow wideo w tej liscie")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--window-start", type=float, default=5.0, help="tylko dla plikow wideo w tej liscie")
    ap.add_argument("--window-len", type=float, default=20.0, help="tylko dla plikow wideo w tej liscie")
    ap.add_argument("--lang", choices=["pl", "en"], default=None)
    ap.add_argument(
        "--warianty-root", dest="warianty_root", nargs="*", default=None,
        help="foldery przemialu do rekurencyjnego szukania wariantow obrazow (_IG/RAF/XMP "
        "w innym folderze niz plik bazowy); podaje je cmd_batch",
    )
    ap.add_argument("--cache-root", default=None, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None, on_progress=None) -> int:
    """on_progress(entry) - jak cmd_measure.main; woluje go eyes.cmd_batch
    (--rodzaj assets) do _postep.json."""
    args = parse_args(argv)
    overrides = overrides_from_out(args.out or args.cache_root)
    if args.lang:
        overrides["lang"] = args.lang
    cfg = load_config(args.config, overrides=overrides)
    file_paths = [Path(f).resolve() if Path(f).exists() else Path(f) for f in args.files]

    hash_by_path = {p: keys_mod.hash_4mb(p) for p in file_paths}
    dup_map = keys_mod.find_duplicate_hashes(file_paths)
    unique_paths = [p for p in file_paths if p not in dup_map]

    project_cache = Path(cfg.cache_root) / args.project
    log_path = project_cache / "_log.jsonl"

    # jedno obejscie drzewa na caly przemial (nie na plik), patrz cmd_photo
    variant_index = photo_mod.zbuduj_indeks_wariantow(args.warianty_root) if args.warianty_root else None

    video_args = argparse.Namespace(
        project=args.project, force=args.force,
        window_start=args.window_start, window_len=args.window_len, no_gpu=args.no_gpu,
    )

    any_failed = False
    total = len(file_paths)

    def _log_i_postep(entry: dict, idx: int) -> None:
        measure_mod.append_log(log_path, entry)
        if on_progress:
            try:
                on_progress({**entry, "i": idx, "n": total})
            except Exception as e:  # noqa: BLE001
                print(f"on_progress: {e}", file=sys.stderr)

    for idx, path in enumerate(file_paths, 1):
        if path in dup_map:
            original = dup_map[path]
            print(f"{path.name}: POMINIETO, identyczny hash_4mb jak {original.name} (duplikat)")
            _log_i_postep({
                "id": keys_mod.compute_id(original, unique_paths),
                "plik": path.name,
                "sciezka_rel": str(path).replace("\\", "/"),
                "status": "duplikat",
                "duplikat_of": str(original).replace("\\", "/"),
                "hash_4mb": hash_by_path[path],
                "czas_calkowity_s": None,
                "data": datetime.datetime.now().astimezone().isoformat(),
                "wersja_metryk": "0.2",
            }, idx)
            continue
        try:
            result = measure_asset(
                path, project=args.project, cfg=cfg, force=args.force,
                hash_by_path=hash_by_path, file_paths=unique_paths,
                video_args=video_args, lut_override=args.lut,
                variant_index=variant_index,
            )
            entry = {
                "id": result["id"],
                "plik": result["plik"],
                "status": result["status"],
                "czas_calkowity_s": result["czas_calkowity_s"],
                "data": datetime.datetime.now().astimezone().isoformat(),
                "wersja_metryk": "0.2",
            }
            if result.get("powod"):
                entry["powod"] = result["powod"]
            _log_i_postep(entry, idx)
        except Exception as e:  # noqa: BLE001
            any_failed = True
            print(f"{path.name}: BLAD {e}", file=sys.stderr)
            _log_i_postep({
                "id": keys_mod.compute_id(path, unique_paths),
                "plik": path.name,
                "status": "blad",
                "czas_calkowity_s": None,
                "error": str(e),
                "data": datetime.datetime.now().astimezone().isoformat(),
                "wersja_metryk": "0.2",
            }, idx)
            continue

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
