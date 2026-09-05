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
rozdzielczosci zamiast tylko na probkowanych.
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


def _build_filter(scaled_w: int, scaled_h: int, fps: float, lut_name: str | None, grayscale: bool) -> str:
    parts = [f"fps={fps}"]
    if lut_name:
        parts.append("format=rgb24")
        parts.append(f"lut3d=file={lut_name}")
    parts.append(f"scale={scaled_w}:{scaled_h}")
    parts.append("format=gray" if grayscale else "format=rgb24")
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
) -> dict:
    """Dekoduje okno [start_s, start_s+duration_s) na klatki numpy.

    Zwraca dict: frames (n,h,w,3) uint8 albo (n,h,w) gdy grayscale, gpu_used,
    gpu_fallback, decode_time_s, width, height.
    """
    scaled_w, scaled_h = compute_scaled_size(orig_w, orig_h, target_w)
    vf = _build_filter(scaled_w, scaled_h, fps, lut_name, grayscale)
    channels = 1 if grayscale else 3
    pix_fmt = "gray" if grayscale else "rgb24"
    cwd = lut_dir if lut_name else None

    def cmd_for(gpu: bool) -> list[str]:
        c = [FFMPEG, "-hide_banner", "-loglevel", "error"]
        if gpu:
            c += ["-hwaccel", "cuda"]
        c += [
            "-ss", f"{start_s}", "-t", f"{duration_s}", "-i", str(input_path),
            "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix_fmt, "-",
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
