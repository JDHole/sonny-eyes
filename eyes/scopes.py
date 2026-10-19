"""Miniaturki PNG (z juz zdekodowanych klatek numpy) i skopy PNG (bezposrednio z ffmpeg)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2

FFMPEG = "ffmpeg"
MAX_KB = 500


def save_thumbnail(frame_rgb, path: Path, max_kb: int = MAX_KB) -> Path:
    """Zapisuje klatke RGB (numpy, juz w szerokosci 480px) jako PNG. Jesli
    wynik > max_kb, dogrywa mniejsza wersje (szerokosc 360px)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), bgr)
    if path.stat().st_size > max_kb * 1024:
        h, w = frame_rgb.shape[:2]
        new_w = 360
        new_h = round(h * new_w / w)
        if new_h % 2:
            new_h += 1
        small = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(path), small)
    return path


def render_scope(
    input_path: str,
    t_s: float,
    filter_name: str,
    out_path: Path,
    lut_dir: str | None = None,
    lut_name: str | None = None,
    max_width: int = 720,
    max_kb: int = MAX_KB,
) -> Path:
    """Renderuje pojedyncza klatke ze skopem (waveform/vectorscope) ffmpegiem.

    vectorscope wymaga jawnej konwersji do yuv420p przed filtrem (inaczej
    ffmpeg 8.0.1 nie potrafi wynegocjowac formatow: "could not choose their
    formats"); waveform dziala wprost na rgb24.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = lut_dir if lut_name else None

    def build(width: int) -> str:
        # format=rgb24 zawsze na wejsciu (nie tylko gdy jest LUT) - bez tego
        # klatka zostaje w natywnym formacie dekodera (np. 10-bit
        # yuv422p10le F-Log Fuji), a waveform go nie akceptuje wprost (patrz
        # README "vectorscope a waveform" - to samo dotyczy w praktyce
        # waveform na materiale bez LUT, ujawnione dopiero pomiarem bez
        # skonfigurowanego LUT-a).
        parts = ["format=rgb24"]
        if lut_name:
            parts.append(f"lut3d=file={lut_name}")
        parts.append(f"scale={width}:-2")
        if filter_name == "vectorscope":
            parts.append("format=yuv420p")
        parts.append(filter_name)
        return ",".join(parts)

    last_stderr = b""
    for width in (max_width, 480):
        vf = build(width)
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t_s}", "-i", str(input_path),
            "-vf", vf, "-frames:v", "1", str(out_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size <= max_kb * 1024:
            return out_path
        last_stderr = result.stderr

    if not out_path.exists():
        raise RuntimeError(
            f"ffmpeg nie wygenerowal skopu {filter_name} dla {input_path}: "
            f"{last_stderr.decode('utf-8', errors='replace')}"
        )
    return out_path


def render_scope_still(
    input_path: str,
    filter_name: str,
    out_path: Path,
    max_width: int = 1024,
    max_kb: int = MAX_KB,
) -> Path:
    """Jak render_scope, ale dla NIERUCHOMEGO obrazu (foto/image, kontrakt
    2026-09-12): bez -ss/-t (caly plik to jedna klatka), bez LUT. `format=
    yuv420p` idzie ZAWSZE przed filtrem skopu (nie tylko dla vectorscope jak
    w render_scope) - inaczej ffmpeg 8.0.1 nie dobiera formatow dla waveform/
    parade/histogram na obrazach. `input_path` idzie przez `-i` (nie przez
    filtrgraf), wiec dwukropek po literze dysku Windows nie psuje parsera
    (patrz modul docstring i CLAUDE.md sesji foto/audio)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def build(width: int) -> str:
        return f"scale={width}:-2,format=yuv420p,{filter_name}"

    last_stderr = b""
    for width in (max_width, 640):
        vf = build(width)
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(input_path), "-vf", vf, "-frames:v", "1", str(out_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size <= max_kb * 1024:
            return out_path
        last_stderr = result.stderr

    if not out_path.exists():
        raise RuntimeError(
            f"ffmpeg nie wygenerowal skopu foto {filter_name} dla {input_path}: "
            f"{last_stderr.decode('utf-8', errors='replace')}"
        )
    return out_path


def render_wave(input_path: str, out_path: Path, size: str = "1600x400", color: str = "9fd39f") -> Path:
    """Fala audio (showwavespic) - jedna klatka PNG w rozmiarze `size`
    ("SxW", np. "1600x400" na fale, "640x160" na kafel). Kolor domyslny
    dopasowany do --wave w CSS strony przegladu (eyes/cmd_review.py)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-filter_complex", f"showwavespic=s={size}:colors=0x{color}",
        "-frames:v", "1", str(out_path),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"ffmpeg nie wygenerowal fali audio dla {input_path}: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return out_path
