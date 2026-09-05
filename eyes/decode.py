"""ffmpeg -> klatki numpy przez pipe (rawvideo), z opcjonalnym lut3d i GPU/CPU fallback.

Uwaga na LUT: bezposrednie wstawienie sciezki Windows (z dwukropkiem po literze
dysku) do filtra lut3d lamie parser filtergraphu tego builda ffmpeg (8.0.1)
nawet po escapowaniu dwukropka. Obejscie: LUT jest kopiowany raz do
{cache_root}/_luts/ (patrz ensure_lut_cached), a ffmpeg jest odpalany z cwd
ustawionym na ten katalog i referencja do LUT-a to sama nazwa pliku (bez
dwukropka, bez spacji do escapowania).

Kolejnosc filtrow: fps NAJPIERW (dropuje klatki tanio), dopiero potem
format/lut3d/scale na tych juz przetrzebionych klatkach - inaczej lut3d
(kosztowna interpolacja 3D) liczy sie na kazdej zdekodowanej klatce w pelnej
rozdzielczosci zamiast tylko na probkowanych. To jest OK dla okna A (max ~40
klatek) - patrz `lut_after_scale`/`long_range` nizej dla dlugich zakresow
(cala dlugosc klipu, do 180 s), gdzie lut3d MUSI dzialac na juz zmniejszonych
klatkach (480 px), inaczej interpolacja 3D na kazdej z nawet ~1800 klatek w
pelnej rozdzielczosci 4K zjada budzet czasowy pomiaru.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

FFMPEG = "ffmpeg"


def ensure_lut_cached(lut_path: str, cache_root: Path) -> tuple[str, str]:
    """Kopiuje LUT do {cache_root}/_luts/ (jesli jeszcze nie ma / rozmiar sie
    zmienil). Zwraca (katalog_lutow, nazwa_pliku) do uzycia jako cwd + file=.
    """
    src = Path(lut_path)
    luts_dir = Path(cache_root) / "_luts"
    luts_dir.mkdir(parents=True, exist_ok=True)
    dst = luts_dir / src.name
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dst)
    return str(luts_dir), src.name


def compute_scaled_size(orig_w: int, orig_h: int, target_w: int) -> tuple[int, int]:
    """Wysokosc proporcjonalna do target_w, zaokraglona do parzystej."""
    h = round(orig_h * target_w / orig_w)
    if h % 2 == 1:
        h += 1
    return target_w, h


def _build_filter(
    scaled_w: int, scaled_h: int, fps: float, lut_name: str | None, grayscale: bool,
    lut_after_scale: bool = False,
) -> str:
    """`lut_after_scale=True` przesuwa `lut3d` ZA `scale` (LUT na malych,
    480px klatkach zamiast na pelnej rozdzielczosci zrodla) - patrz modul
    docstring. Uzywane dla dlugich zakresow (`decode_frames(..., long_range=
    True)`); domyslnie False zachowuje dotychczasowa kolejnosc (okno A)."""
    parts = [f"fps={fps}"]
    if lut_name and not lut_after_scale:
        parts.append("format=rgb24")
        parts.append(f"lut3d=file={lut_name}")
    parts.append(f"scale={scaled_w}:{scaled_h}")
    if lut_name and lut_after_scale:
        parts.append("format=rgb24")
        parts.append(f"lut3d=file={lut_name}")
        if grayscale:
            parts.append("format=gray")
        return ",".join(parts)
    parts.append("format=gray" if grayscale else "format=rgb24")
    return ",".join(parts)


def _build_filter_gpu_smallfirst(
    scaled_w: int, scaled_h: int, fps: float, lut_name: str | None, grayscale: bool,
) -> str:
    """Wariant GPU 'male klatki najpierw': `scale_cuda` + `hwdownload` (i LUT,
    jesli dotyczy) PRZED `fps`, odwrotnie niz w `_build_filter`. Bez tego,
    dla dlugich zakresow (caly klip, do 180 s) `fps` (ktory nie ma wariantu
    CUDA) wymusza `hwdownload` KAZDEJ zdekodowanej klatki w pelnej
    rozdzielczosci zrodla, zanim cokolwiek moze zostac odrzucone - `fps` w
    filtergraphie odrzuca klatki PO dekodowaniu/hwdownload, nie przed.
    Skalujac NAJPIERW na GPU do docelowych ~480 px, `hwdownload` dziala na
    malych klatkach - dla dlugich zakresow to realna oszczednosc (zmierzone
    bez LUT: ~28% szybciej na 115 s klipu 4K 10-bit; patrz README 'Metryka
    ruchu v0.2' pkt 7). Bez LUT (`lut_name=None`) daje dokladnie ten sam
    filtrgraf co dawniejsze `_build_filter_gpu_gray` (fps na koncu - tania
    konwersja formatu, nie ma powodu przycinac przed nia). Z LUT: `fps`
    (dropujac do docelowego fps) idzie PRZED `lut3d`, zeby kosztowna
    interpolacja 3D dostala tylko faktycznie probkowane male klatki, a nie
    kazda natywna klatke zrodla - "male klatki" (ten wariant) + "male fps"
    (kolejnosc filtrow) razem. Wymaga wywolania z `-hwaccel_output_format
    cuda`."""
    parts = [f"scale_cuda=w={scaled_w}:h={scaled_h}:format=nv12", "hwdownload", "format=nv12"]
    if lut_name:
        parts.append("format=rgb24")
        parts.append(f"fps={fps}")
        parts.append(f"lut3d=file={lut_name}")
        if grayscale:
            parts.append("format=gray")
        return ",".join(parts)
    parts.append("format=gray" if grayscale else "format=rgb24")
    parts.append(f"fps={fps}")
    return ",".join(parts)


def _run(cmd: list[str], cwd: str | None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)


def decode_frames(
    input_path: str,
    start_s: float,
    duration_s: float,
    fps: float,
    orig_w: int,
    orig_h: int,
    target_w: int = 480,
    lut_dir: str | None = None,
    lut_name: str | None = None,
    grayscale: bool = False,
    use_gpu: bool = True,
    long_range: bool = False,
) -> dict:
    """Dekoduje okno [start_s, start_s+duration_s) na klatki numpy.

    `long_range=True` (uzywane przy pelnej dlugosci klipu, do 180 s - ruch +
    tonalnosc.profil) przelacza na filtrgraf 'male klatki najpierw': z GPU -
    `_build_filter_gpu_smallfirst` (scale_cuda+hwdownload przed fps), bez GPU
    (fallback CPU) - `_build_filter` z `lut_after_scale=True` (lut3d po scale,
    nie przed). Domyslnie (False, okno A) zachowuje dotychczasowy filtrgraf
    bez zmian.

    Zwraca dict: frames (n,h,w,3) uint8 albo (n,h,w) gdy grayscale, gpu_used,
    gpu_fallback, decode_time_s, width, height.
    """
    scaled_w, scaled_h = compute_scaled_size(orig_w, orig_h, target_w)
    vf = _build_filter(scaled_w, scaled_h, fps, lut_name, grayscale, lut_after_scale=long_range)
    channels = 1 if grayscale else 3
    pix_fmt = "gray" if grayscale else "rgb24"
    cwd = lut_dir if lut_name else None

    # long_range + GPU: uzyj scale_cuda-przed-fps (patrz
    # _build_filter_gpu_smallfirst). Okno A albo brak GPU (fallback CPU):
    # `vf` powyzej (z lut_after_scale wg long_range).
    gpu_smallfirst_vf = (
        _build_filter_gpu_smallfirst(scaled_w, scaled_h, fps, lut_name, grayscale)
        if long_range else None
    )

    def cmd_for(gpu: bool) -> list[str]:
        c = [FFMPEG, "-hide_banner", "-loglevel", "error"]
        if gpu:
            c += ["-hwaccel", "cuda"]
            if gpu_smallfirst_vf:
                c += ["-hwaccel_output_format", "cuda"]
        vf_use = gpu_smallfirst_vf if (gpu and gpu_smallfirst_vf) else vf
        c += [
            "-ss", f"{start_s}", "-t", f"{duration_s}", "-i", str(input_path),
            "-vf", vf_use, "-f", "rawvideo", "-pix_fmt", pix_fmt, "-",
        ]
        return c

    gpu_used = False
    gpu_fallback = False
    t0 = time.perf_counter()
    if use_gpu:
        result = _run(cmd_for(True), cwd)
        if result.returncode != 0:
            gpu_fallback = True
            result = _run(cmd_for(False), cwd)
        else:
            gpu_used = True
    else:
        result = _run(cmd_for(False), cwd)
    decode_time_s = time.perf_counter() - t0

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg nie powiodl sie dla {input_path}: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )

    raw = result.stdout
    frame_size = scaled_h * scaled_w * channels
    n_frames = len(raw) // frame_size
    arr = np.frombuffer(raw[: n_frames * frame_size], dtype=np.uint8)
    if grayscale:
        arr = arr.reshape(n_frames, scaled_h, scaled_w)
    else:
        arr = arr.reshape(n_frames, scaled_h, scaled_w, channels)

    return {
        "frames": arr,
        "gpu_used": gpu_used,
        "gpu_fallback": gpu_fallback,
        "decode_time_s": decode_time_s,
        "width": scaled_w,
        "height": scaled_h,
    }
