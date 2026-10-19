"""ffprobe -> dict z parametrami strumienia wideo."""
from __future__ import annotations

import json
import subprocess


def _parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "N/A"):
        return None
    try:
        num_s, _, den_s = rate.partition("/")
        num = float(num_s)
        den = float(den_s) if den_s else 1.0
        if den == 0:
            return None
        return num / den
    except (ValueError, TypeError):
        return None


def probe(path: str, ffprobe_exe: str = "ffprobe") -> dict:
    """Zwraca: codec, w, h, fps (r_frame_rate), fps_avg (avg_frame_rate),
    pix_fmt, range, transfer, primaries, duration_s, nb_frames.
    """
    cmd = [
        ffprobe_exe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe nie powiodl sie dla {path}: {result.stderr}")

    data = json.loads(result.stdout)
    vstream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if vstream is None:
        raise RuntimeError(f"brak strumienia wideo w {path}")
    fmt = data.get("format", {})

    duration_s = None
    if fmt.get("duration") not in (None, "N/A"):
        duration_s = float(fmt["duration"])
    elif vstream.get("duration") not in (None, "N/A"):
        duration_s = float(vstream["duration"])

    nb_frames = None
    nb_frames_raw = vstream.get("nb_frames")
    if nb_frames_raw is not None and str(nb_frames_raw).isdigit():
        nb_frames = int(nb_frames_raw)

    return {
        "codec": vstream.get("codec_name"),
        "w": vstream.get("width"),
        "h": vstream.get("height"),
        "fps": _parse_rate(vstream.get("r_frame_rate")),
        "fps_avg": _parse_rate(vstream.get("avg_frame_rate")),
        "pix_fmt": vstream.get("pix_fmt"),
        "range": vstream.get("color_range"),
        "transfer": vstream.get("color_transfer"),
        "primaries": vstream.get("color_primaries"),
        "duration_s": duration_s,
        "nb_frames": nb_frames,
    }


def probe_audio(path: str, ffprobe_exe: str = "ffprobe") -> dict:
    """Jak probe(), ale dla pliku audio (kontrakt foto/audio 2026-09-12):
    codec, sample_rate, channels, bits (z bits_per_sample/bits_per_raw_sample,
    None gdy kontener nie deklaruje), duration_s. Nie wymaga strumienia wideo."""
    cmd = [
        ffprobe_exe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe nie powiodl sie dla {path}: {result.stderr}")

    data = json.loads(result.stdout)
    astream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if astream is None:
        raise RuntimeError(f"brak strumienia audio w {path}")
    fmt = data.get("format", {})

    duration_s = None
    if fmt.get("duration") not in (None, "N/A"):
        duration_s = float(fmt["duration"])
    elif astream.get("duration") not in (None, "N/A"):
        duration_s = float(astream["duration"])

    bits = astream.get("bits_per_sample") or astream.get("bits_per_raw_sample")
    bits = int(bits) if bits not in (None, 0, "0") else None

    sample_rate = astream.get("sample_rate")
    sample_rate = int(sample_rate) if sample_rate is not None else None

    return {
        "codec": astream.get("codec_name"),
        "sample_rate": sample_rate,
        "channels": astream.get("channels"),
        "bits": bits,
        "duration_s": duration_s,
    }
