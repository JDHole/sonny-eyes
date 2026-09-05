"""Metryki v0: tonalnosc, kolor, ostrosc, szum, ruch, plynnosc, montaz, flagi.

Progi klasyfikacji ruchu i flag sa PROWIZORYCZNE (literaturowe zgrubne
przyblizenia, nie kalibrowane na materiale Kuby) - patrz PROGI_PROWIZORYCZNE
nizej, zapisywane tez do raportu w polu progi_prowizoryczne.
"""
from __future__ import annotations

import cv2
import numpy as np

PROGI_PROWIZORYCZNE = {
    "jitter_static_max": 0.05,
    "ruch_static_max": 0.2,
    "jitter_handheld_max": 0.3,
    "ruch_pan_min": 1.0,
    "clip_hi_pct_max": 1.0,
    "p5_czern_mleczna_max": 0.06,
    "p1_czern_zabita_max": 0.005,
    "clip_lo_pct_czern_zabita_min": 2.0,
    "lapvar_nieostre_max": 5.0,
    "jitter_trzesie_min": 0.3,
}


def to_luma709(frames_rgb: np.ndarray) -> np.ndarray:
    """(n,h,w,3) uint8 RGB -> (n,h,w) float64 luma BT.709 w 0..1."""
    f = frames_rgb.astype(np.float64) / 255.0
    return 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]


def compute_tonalnosc(frames_rgb: np.ndarray) -> dict:
    y = to_luma709(frames_rgb)
    flat = y.reshape(-1)
    p1, p5, p50, p95, p99 = np.percentile(flat, [1, 5, 50, 95, 99])
    clip_lo_pct = float(100.0 * np.mean(flat < 0.01))
    clip_hi_pct = float(100.0 * np.mean(flat > 0.99))
    kontrast_rms = float(np.std(flat))
    medians = np.median(y.reshape(y.shape[0], -1), axis=1)
    p50_rozrzut = float(np.std(medians))
    return {
        "p1": float(p1), "p5": float(p5), "p50": float(p50),
        "p95": float(p95), "p99": float(p99),
        "clip_lo_pct": clip_lo_pct, "clip_hi_pct": clip_hi_pct,
        "kontrast_rms": kontrast_rms, "p50_rozrzut": p50_rozrzut,
    }


def compute_kolor(frames_rgb: np.ndarray) -> dict:
    f = frames_rgb.astype(np.float32) / 255.0
    sat_frames = [cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)[..., 1] for frame in f]
    sat_all = np.stack(sat_frames).reshape(-1)
    sat_mean = float(np.mean(sat_all))
    sat_p95 = float(np.percentile(sat_all, 95))

    mean_r = float(np.mean(f[..., 0]))
    mean_g = float(np.mean(f[..., 1]))
    mean_b = float(np.mean(f[..., 2]))
    cast_rg = mean_r - mean_g
    cast_bg = mean_b - mean_g

    cct_est_k = None
    try:
        import colour
        rgb_mean = np.array([mean_r, mean_g, mean_b])
        xyz = colour.sRGB_to_XYZ(rgb_mean)
        xy = colour.XYZ_to_xy(xyz)
        cct = colour.xy_to_CCT(xy, method="McCamy 1992")
        cct_val = float(cct)
        if np.isfinite(cct_val):
            cct_est_k = cct_val
    except Exception:
        cct_est_k = None

    return {
        "sat_mean": sat_mean, "sat_p95": sat_p95,
        "cast_rg": cast_rg, "cast_bg": cast_bg,
        "cct_est_k": cct_est_k,
    }


def compute_ostrosc(frames_rgb: np.ndarray) -> tuple[dict, int]:
    """Zwraca (metryki_ostrosci, indeks_najostrzejszej_klatki)."""
    grays = [cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY) for frame in frames_rgb]
    lapvars = np.array([cv2.Laplacian(g, cv2.CV_64F).var() for g in grays])
    idx_sharp = int(np.argmax(lapvars))
    sharp = grays[idx_sharp]
    h, w = sharp.shape
    hs = [0, h // 3, 2 * h // 3, h]
    ws = [0, w // 3, 2 * w // 3, w]
    siatka = []
    for i in range(3):
        for j in range(3):
            cell = sharp[hs[i]:hs[i + 1], ws[j]:ws[j + 1]]
            siatka.append(float(cv2.Laplacian(cell, cv2.CV_64F).var()))
    metryki = {
        "lapvar": float(np.mean(lapvars)),
        "lapvar_min": float(np.min(lapvars)),
        "lapvar_max": float(np.max(lapvars)),
        "siatka_3x3": siatka,
        "skala_pomiaru_px": 480,
    }
    return metryki, idx_sharp


def compute_szum(sharp_frame_rgb: np.ndarray) -> dict:
    try:
        from skimage.restoration import estimate_sigma
        img = sharp_frame_rgb.astype(np.float64) / 255.0
        sigma = estimate_sigma(img, channel_axis=-1, average_sigmas=True)
        sigma_val = float(sigma)
        if not np.isfinite(sigma_val):
            return {"sigma": None}
        return {"sigma": sigma_val}
    except Exception:
        return {"sigma": None}


def _moving_average(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(x) == 0:
        return x.copy()
    kernel = np.ones(window)
    sums = np.convolve(x, kernel, mode="same")
    counts = np.convolve(np.ones_like(x), kernel, mode="same")
    return sums / counts


def compute_ruch(frames_gray_b: np.ndarray, fps_b: float, target_width: int) -> dict:
    n = frames_gray_b.shape[0]
    if n < 3:
        return {
            "ruch_zamierzony_pct_s": None, "jitter_rms_pct": None,
            "klasa": ["nieznana"], "zrodlo": "phase_correlation",
        }
    h, w = frames_gray_b.shape[1:3]
    hann = cv2.createHanningWindow((w, h), cv2.CV_32F)
    mags = []
    for i in range(n - 1):
        a = frames_gray_b[i].astype(np.float32)
        b = frames_gray_b[i + 1].astype(np.float32)
        (dx, dy), _resp = cv2.phaseCorrelate(a * hann, b * hann)
        mags.append(float(np.hypot(dx, dy)))
    mags = np.array(mags)

    window = max(1, round(0.5 * fps_b))
    ma = _moving_average(mags, window)

    ruch_zamierzony_pct_s = float(np.mean(np.abs(ma)) * fps_b / target_width * 100.0)
    residual = mags - ma
    jitter_rms_pct = float(np.sqrt(np.mean(residual ** 2)) / target_width * 100.0)

    if jitter_rms_pct < PROGI_PROWIZORYCZNE["jitter_static_max"] and ruch_zamierzony_pct_s < PROGI_PROWIZORYCZNE["ruch_static_max"]:
        klasa = ["static"]
    elif jitter_rms_pct < PROGI_PROWIZORYCZNE["jitter_handheld_max"]:
        klasa = ["handheld"]
    else:
        klasa = ["shaky"]
    if ruch_zamierzony_pct_s > PROGI_PROWIZORYCZNE["ruch_pan_min"]:
        klasa.append("pan")

    return {
        "ruch_zamierzony_pct_s": ruch_zamierzony_pct_s,
        "jitter_rms_pct": jitter_rms_pct,
        "klasa": klasa,
        "zrodlo": "phase_correlation",
    }


def compute_plynnosc(frames_gray_b: np.ndarray, fps: float | None, fps_avg: float | None) -> dict:
    vfr = bool(fps is not None and fps_avg is not None and abs(fps - fps_avg) > 1e-6)
    n = frames_gray_b.shape[0]
    diffs = []
    for i in range(n - 1):
        a = frames_gray_b[i].astype(np.float64) / 255.0
        b = frames_gray_b[i + 1].astype(np.float64) / 255.0
        diffs.append(float(np.mean(np.abs(a - b))))
    diffs = np.array(diffs) if diffs else np.array([])
    duplikaty = int(np.sum(diffs < 0.002)) if diffs.size else 0
    tdiff = float(np.mean(diffs)) if diffs.size else None
    return {"vfr": vfr, "duplikaty": duplikaty, "tdiff": tdiff}


def compute_montaz(duration_s: float) -> dict:
    return {"dlugosc_s": duration_s, "segmenty": []}


def compute_flagi(tonalnosc: dict, ostrosc: dict, ruch: dict) -> list[str]:
    flagi = []
    if tonalnosc["clip_hi_pct"] > PROGI_PROWIZORYCZNE["clip_hi_pct_max"]:
        flagi.append("clip_hi>1%")
    if tonalnosc["p5"] > PROGI_PROWIZORYCZNE["p5_czern_mleczna_max"]:
        flagi.append("czern_mleczna")
    if (tonalnosc["p1"] < PROGI_PROWIZORYCZNE["p1_czern_zabita_max"]
            and tonalnosc["clip_lo_pct"] > PROGI_PROWIZORYCZNE["clip_lo_pct_czern_zabita_min"]):
        flagi.append("czern_zabita")
    if ostrosc["lapvar"] < PROGI_PROWIZORYCZNE["lapvar_nieostre_max"]:
        flagi.append("nieostre")
    if ruch.get("jitter_rms_pct") is not None and ruch["jitter_rms_pct"] >= PROGI_PROWIZORYCZNE["jitter_trzesie_min"]:
        flagi.append("trzesie")
    return flagi
