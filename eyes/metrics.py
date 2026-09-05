"""Metryki v0.2: tonalnosc, kolor, ostrosc, szum, ruch, plynnosc, montaz, flagi.

Progi klasyfikacji ruchu i flag sa PROWIZORYCZNE (kalibrowane recznie na 3
klipach werdyktowych Kuby z 2026-09-05, nie na pelnej probce) - patrz
PROGI_PROWIZORYCZNE nizej, zapisywane tez do raportu w polu progi_prowizoryczne.
"""
from __future__ import annotations

import cv2
import numpy as np

PROGI_PROWIZORYCZNE = {
    # S: prog stabilnosci sekundy/agregatu na jitterze (jitter_pct < S -> stabilne).
    # Podniesiony 0.15 -> 0.4 po kalibracji na DSCF1414: realne "polozone na
    # murku" ujecie z aktywnym obiektem w kadrze (czlowiek balansujacy) ma
    # jitter rzedu 0.02-0.15 caly czas plus pojedyncze doskoki do ~0.3-0.36 -
    # 0.15 fragmentowalo jeden dlugi stabilny odcinek na kilkanascie krotkich.
    "jitter_stabilny_max": 0.4,
    # R: prog stabilnosci/pan na ruchu zamierzonym (< R stabilne, > R -> "pan").
    # Podniesiony 1.0 -> 3.0 z tego samego powodu co S - ruch_pct tej samej
    # sceny miescil sie w ~0.3-2.6%/s poza pierwszymi ~22 s (prawdziwym
    # ruchem), 1.0 bylo za nisko.
    "ruch_stabilny_max": 3.0,
    # granica handheld/shaky na jitterze SRODKA (RMS, sekundy poza pierwszymi/
    # ostatnimi 2 s klipu)
    "jitter_shaky_min": 0.6,
    "clip_hi_pct_max": 1.0,
    "p5_czern_mleczna_max": 0.06,
    "p1_czern_zabita_max": 0.005,
    "clip_lo_pct_czern_zabita_min": 2.0,
    "lapvar_nieostre_max": 5.0,
}

# Plan probkowania ruchu (patrz plan_probkowania_ruchu): caly klip od 0 s,
# 10 kl/s do 60 s klipu / 5 kl/s powyzej, twardy limit 180 s materialu.
RUCH_FPS_KROTKI = 10
RUCH_FPS_DLUGI = 5
RUCH_PROG_DLUGOSCI_S = 60.0
RUCH_MAX_S = 180.0

# Parametry sledzenia cech (goodFeaturesToTrack + LK) i bramki pewnosci pary.
GFTT_MAX_CORNERS = 400
GFTT_QUALITY = 0.01
GFTT_MIN_DIST = 8
LK_WIN = (21, 21)
LK_MAX_LEVEL = 3
LK_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
RANSAC_PROG_PX = 3.0
MIN_PUNKTOW = 12
MIN_INLIER_RATIO = 0.30

# Minimalna pewnosc (srednia inlier_ratio par w sekundzie) zeby sekunda mogla
# POTWIERDZIC niestabilnosc brzegu (ruch.brzegi). Bez tego rozpad trackingu
# (np. reka zaslaniajaca obiektyw przy zatrzymywaniu nagrania - konf < 0.1,
# wartosc "ruch_pct" bez sensu fizycznego) falszywie udaje koniec_ruch=true
# na klipach ktore poza tym sa czysto statyczne (zlapane na DSCF2988). Sama
# wartosc >= R nie wystarcza - potrzebna tez pewnosc pomiaru.
MIN_CONF_BRZEG = 0.30


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


def plan_probkowania_ruchu(duration_s: float) -> tuple[float, float, float | None]:
    """Plan probkowania B (ruch): caly klip od 0 s, nie pierwsze 5 s.

    10 kl/s dla klipow do 60 s, 5 kl/s powyzej; twardy limit 180 s materialu.
    Zwraca (fps_b, dlugosc_do_dekodowania_s, obciete_s): obciete_s = 180.0
    gdy klip byl dluzszy i zostal obciety, inaczej None.
    """
    fps_b = RUCH_FPS_KROTKI if duration_s <= RUCH_PROG_DLUGOSCI_S else RUCH_FPS_DLUGI
    if duration_s > RUCH_MAX_S:
        return float(fps_b), RUCH_MAX_S, RUCH_MAX_S
    return float(fps_b), float(duration_s), None


def _moving_average(x: np.ndarray, window: int) -> np.ndarray:
    """Ruchoma srednia z oknem `window` probek. NaN (pary niepewne/brakujace)
    sa pomijane w liczniku i mianowniku; pozycja bez zadnej wartosci w oknie
    -> NaN. Bez NaN w wejsciu dziala identycznie jak zwykla ruchoma srednia."""
    if window <= 1 or len(x) == 0:
        return x.copy()
    mask = ~np.isnan(x)
    x0 = np.where(mask, x, 0.0)
    kernel = np.ones(window)
    sums = np.convolve(x0, kernel, mode="same")
    counts = np.convolve(mask.astype(np.float64), kernel, mode="same")
    with np.errstate(invalid="ignore", divide="ignore"):
        ma = np.where(counts > 0, sums / counts, np.nan)
    return ma


def _ruch_pary(gray_a: np.ndarray, gray_b: np.ndarray) -> dict:
    """Ruch kamery miedzy dwiema probkami (n,h,w) uint8: cechy
    (goodFeaturesToTrack) + optical flow (calcOpticalFlowPyrLK) + afiniczna
    transformacja RANSAC (estimateAffinePartial2D) na cechach TLA - odrzuca
    jako outliery punkty na ruchomych obiektach (liscie, ludzie), zostawiajac
    ruch kamery. None (pewna=False) gdy < 12 sledzonych punktow albo
    < 30% inlierow RANSAC."""
    pusta = {"pewna": False, "dx_px": None, "dy_px": None,
             "rotacja_deg": None, "skala": None, "inlier_ratio": 0.0}
    try:
        pts0 = cv2.goodFeaturesToTrack(gray_a, GFTT_MAX_CORNERS, GFTT_QUALITY, GFTT_MIN_DIST)
        if pts0 is None or len(pts0) < MIN_PUNKTOW:
            return pusta

        pts1, status, _err = cv2.calcOpticalFlowPyrLK(
            gray_a, gray_b, pts0, None,
            winSize=LK_WIN, maxLevel=LK_MAX_LEVEL, criteria=LK_CRITERIA,
        )
        mask = status.reshape(-1).astype(bool)
        good0, good1 = pts0[mask], pts1[mask]
        if len(good0) < MIN_PUNKTOW:
            return pusta

        M, inliers = cv2.estimateAffinePartial2D(
            good0, good1, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PROG_PX,
        )
        if M is None:
            return pusta

        inlier_ratio = float(inliers.mean()) if inliers is not None and len(inliers) else 0.0
        if inlier_ratio < MIN_INLIER_RATIO:
            return {**pusta, "inlier_ratio": inlier_ratio}

        return {
            "pewna": True,
            "dx_px": float(M[0, 2]),
            "dy_px": float(M[1, 2]),
            "rotacja_deg": float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))),
            "skala": float(np.hypot(M[0, 0], M[1, 0])),
            "inlier_ratio": inlier_ratio,
        }
    except cv2.error:
        return pusta


def compute_ruch(frames_gray_b: np.ndarray, fps_b: float, target_width: int) -> dict:
    """Ruch kamery (v0.2): LK+RANSAC afiniczny miedzy kolejnymi probkami na
    CALYM probkowanym zakresie (patrz plan_probkowania_ruchu w wywolujacym).
    Profil co sekunde, odcinki stabilne/ruch, klasa liczona ze "srodka"
    (caly klip minus pierwsze/ostatnie 2 s), brzegi osobno. `obcieto_s` NIE
    jest tu ustawiane - dopisuje go wywolujacy (measure.py), bo ta funkcja
    zna tylko juz zdekodowane klatki, nie oryginalna dlugosc klipu."""
    n = frames_gray_b.shape[0]
    pusty = {
        "ruch_zamierzony_pct_s": None, "jitter_rms_pct": None,
        "mediana_jitter_pct": None, "p90_jitter_pct": None,
        "mediana_jitter_srodka_pct": None, "mediana_ruch_srodka_pct": None,
        "profil": [], "odcinki": [], "srodek": None,
        "brzegi": {"poczatek_ruch": False, "koniec_ruch": False},
        "pary_niepewne": 0, "klasa": ["nieznana"], "zrodlo": "lk_ransac_affine",
    }
    if n < 3:
        return pusty

    n_pary = n - 1
    dx_px = np.full(n_pary, np.nan)
    dy_px = np.full(n_pary, np.nan)
    inlier_ratio_arr = np.zeros(n_pary)
    pary_niepewne = 0
    for i in range(n_pary):
        par = _ruch_pary(frames_gray_b[i], frames_gray_b[i + 1])
        inlier_ratio_arr[i] = par["inlier_ratio"]
        if par["pewna"]:
            dx_px[i] = par["dx_px"]
            dy_px[i] = par["dy_px"]
        else:
            pary_niepewne += 1

    mags_px = np.hypot(dx_px, dy_px)  # NaN gdzie para niepewna
    window = max(1, round(0.5 * fps_b))
    ma_px = _moving_average(mags_px, window)
    residual_px = mags_px - ma_px

    fps_b_int = int(round(fps_b))
    n_sec = (n_pary + fps_b_int - 1) // fps_b_int

    profil = []
    for sek in range(n_sec):
        i0, i1 = sek * fps_b_int, min((sek + 1) * fps_b_int, n_pary)
        ma_sub = ma_px[i0:i1]
        res_sub = residual_px[i0:i1]
        conf_sub = inlier_ratio_arr[i0:i1]
        ma_valid = ma_sub[~np.isnan(ma_sub)]
        res_valid = res_sub[~np.isnan(res_sub)]
        ruch_pct = float(np.mean(np.abs(ma_valid)) * fps_b / target_width * 100.0) if ma_valid.size else None
        jitter_pct = float(np.sqrt(np.mean(res_valid ** 2)) / target_width * 100.0) if res_valid.size else None
        conf = float(np.mean(conf_sub)) if conf_sub.size else 0.0
        profil.append({"t_s": sek, "ruch_pct": ruch_pct, "jitter_pct": jitter_pct, "conf": conf})

    S = PROGI_PROWIZORYCZNE["jitter_stabilny_max"]
    R = PROGI_PROWIZORYCZNE["ruch_stabilny_max"]
    GRANICA = PROGI_PROWIZORYCZNE["jitter_shaky_min"]

    def stabilna(entry: dict) -> bool:
        j, r = entry["jitter_pct"], entry["ruch_pct"]
        return j is not None and r is not None and j < S and r < R

    # Odcinki: scalenie sasiednich sekund o tym samym typie stabilnosci.
    odcinki: list[dict] = []
    for entry in profil:
        typ = "stabilny" if stabilna(entry) else "ruch"
        if odcinki and odcinki[-1]["typ"] == typ:
            odcinki[-1]["do_s"] = entry["t_s"]
        else:
            odcinki.append({"od_s": entry["t_s"], "do_s": entry["t_s"], "typ": typ})

    stabilne = [o for o in odcinki if o["typ"] == "stabilny"]
    if stabilne:
        najdluzszy = max(stabilne, key=lambda o: o["do_s"] - o["od_s"])
        srodek = {"od_s": najdluzszy["od_s"], "do_s": najdluzszy["do_s"]}
    else:
        srodek = None

    # "Srodek" dla agregatow klasy = caly klip MINUS pierwsze/ostatnie 2 s
    # (zakres stały, niezalezny od wykrytego odcinka `srodek` powyzej).
    # Klip < 6 s: agregaty licz z calosci (nie ma z czego wyciac brzegow).
    rozpietosc_s = n_pary / fps_b
    if rozpietosc_s < 6.0:
        idx_srodek = list(range(n_sec))
    else:
        idx_srodek = list(range(2, n_sec - 2))
        if not idx_srodek:
            idx_srodek = list(range(n_sec))
    idx_wszystkie = list(range(n_sec))

    def agg_rms(idxs: list[int]) -> float | None:
        vals = [profil[i]["jitter_pct"] for i in idxs if profil[i]["jitter_pct"] is not None]
        return float(np.sqrt(np.mean(np.square(vals)))) if vals else None

    def agg_mean(idxs: list[int], klucz: str) -> float | None:
        vals = [profil[i][klucz] for i in idxs if profil[i][klucz] is not None]
        return float(np.mean(vals)) if vals else None

    def agg_mediana(idxs: list[int], klucz: str) -> float | None:
        vals = [profil[i][klucz] for i in idxs if profil[i][klucz] is not None]
        return float(np.median(vals)) if vals else None

    jitter_rms_pct = agg_rms(idx_srodek)
    ruch_zamierzony_pct_s = agg_mean(idx_srodek, "ruch_pct")
    mediana_jitter_srodka_pct = agg_mediana(idx_srodek, "jitter_pct")
    # Mediana (nie srednia) ruchu srodka - jak mediana_jitter_srodka_pct,
    # odporna na pojedyncza "zanieczyszczona" sekunde przy granicy przycietego
    # zakresu (np. gdy prawdziwe odlozenie kamery trwa troche dluzej niz 2 s
    # trymu). Uzywana TYLKO w bramce klasy "postawiona" ponizej.
    mediana_ruch_srodka_pct = agg_mediana(idx_srodek, "ruch_pct")

    wszystkie_jitter = [profil[i]["jitter_pct"] for i in idx_wszystkie if profil[i]["jitter_pct"] is not None]
    mediana_jitter_pct = float(np.median(wszystkie_jitter)) if wszystkie_jitter else None
    p90_jitter_pct = float(np.percentile(wszystkie_jitter, 90)) if wszystkie_jitter else None
    # Mediana (nie srednia/RMS) tez dla CALEGO klipu - patrz uzasadnienie przy
    # calosc_stabilna nizej (DSCF2988: pojedyncza zepsuta sekunda na koncu
    # klipu potrafi zdominowac srednia, mediana ja ignoruje).
    calosc_ruch_mediana = agg_mediana(idx_wszystkie, "ruch_pct")

    def zakres_niestabilny(idxs: list[int]) -> bool:
        """True gdy KAZDA sekunda w zakresie jest POTWIERDZONA niestabilna:
        poza progiem I z wystarczajaca pewnoscia pomiaru (conf >=
        MIN_CONF_BRZEG). To NIE jest to samo, co "niestabilna" dla
        odcinkow/srodka (funkcja `stabilna` powyzej) - tam brak/watpliwe dane
        licza sie jako "nie potwierdzono ze stabilne" (konserwatywnie
        przeciw falszywej stabilnosci). Tutaj chodzi o odwrotne ryzyko:
        sekunda bez pewnych par (ruch_pct/jitter_pct None - z definicji ma
        tez conf < MIN_CONF_BRZEG, bo do None dochodzi tylko gdy WSZYSTKIE
        pary w sekundzie mialy inlier_ratio < 30%) albo z wartoscia
        obliczona z niskiej pewnosci (rozpad trackingu, np. reka zaslaniajaca
        obiektyw przy zatrzymywaniu nagrania - conf ~0.2, ruch_pct fizycznie
        bez sensu >100% szerokosci kadru) NIE jest wiarygodnym dowodem
        prawdziwego ruchu kamery - falszywie zaznaczala koniec_ruch na
        czysto statywowym DSCF2988. Wiec taka sekunda NIE potwierdza
        niestabilnosci brzegu (przeciw falszywemu "postawiona"/ruch
        na brzegu)."""
        if not idxs:
            return False
        return all((not stabilna(profil[i])) and profil[i]["conf"] >= MIN_CONF_BRZEG for i in idxs)

    pierwsze_idx = list(range(0, min(2, n_sec)))
    ostatnie_idx = list(range(max(0, n_sec - 2), n_sec))

    # "Srodek stabilny" na potrzeby brzegow I klasy "postawiona" liczony
    # MEDIANA (jitter i ruch), nie srednia/RMS: mediana jest odporna, gdy
    # prawdziwe niestabilne odlozenie/podniesienie kamery jest troche szersze
    # niz 2 s trymu i zanieczyszcza 1 sekunde na krawedzi przycietego zakresu
    # `idx_srodek` - dokladnie ten przypadek, ktory brzegi maja wykrywac.
    srodek_stabilny = (
        mediana_jitter_srodka_pct is not None and mediana_ruch_srodka_pct is not None
        and mediana_jitter_srodka_pct < S and mediana_ruch_srodka_pct < R
    )
    brzegi = {
        "poczatek_ruch": bool(zakres_niestabilny(pierwsze_idx) and srodek_stabilny),
        "koniec_ruch": bool(zakres_niestabilny(ostatnie_idx) and srodek_stabilny),
    }

    # Klasa: postawiona/static/handheld/shaky sa WYKLUCZAJACE (pierwsza
    # pasujaca wygrywa), "pan" jest dodawany niezaleznie. "static" patrzy na
    # CALOSC (bez trymu) - MEDIANA, nie srednia/RMS. Pierwsza wersja uzywala
    # sredniej/RMS z zalozeniem, ze wrazliwosc na krotkie zaburzenie na
    # brzegu jest tu pozadana - ale na DSCF2988 (statyw) pojedyncza zepsuta
    # sekunda tuz przed koncem nagrania (patrz zakres_niestabilny wyzej)
    # dawala ruch_pct > 100%, co samo jedno przebijalo srednia calego 128 s
    # klipu ponad prog R i blokowalo "static" mimo ze 126/128 sekund bylo
    # ewidentnie spokojnych. Mediana ignoruje taki pojedynczy skrajny wyjatek
    # (potrzeba by ~polowy klipu zepsutej, zeby ja ruszyc), a wciaz poprawnie
    # NIE kwalifikuje klipow z rozlegla, prawdziwa niestabilnoscia (np.
    # DSCF1414, gdzie ~20% klipu jest realnie w ruchu - i tak nie dociera tu,
    # bo "postawiona" jest sprawdzane pierwsze i juz pasuje).
    calosc_stabilna = (
        mediana_jitter_pct is not None and calosc_ruch_mediana is not None
        and mediana_jitter_pct < S and calosc_ruch_mediana < R
    )
    ktorykolwiek_brzeg_w_ruchu = brzegi["poczatek_ruch"] or brzegi["koniec_ruch"]

    if srodek_stabilny and ktorykolwiek_brzeg_w_ruchu:
        klasa = ["postawiona"]
    elif calosc_stabilna:
        klasa = ["static"]
    elif jitter_rms_pct is not None and jitter_rms_pct < GRANICA:
        klasa = ["handheld"]
    elif jitter_rms_pct is not None:
        klasa = ["shaky"]
    else:
        klasa = ["nieznana"]

    if ruch_zamierzony_pct_s is not None and ruch_zamierzony_pct_s > R:
        klasa.append("pan")

    return {
        "ruch_zamierzony_pct_s": ruch_zamierzony_pct_s,
        "jitter_rms_pct": jitter_rms_pct,
        "mediana_jitter_pct": mediana_jitter_pct,
        "p90_jitter_pct": p90_jitter_pct,
        "mediana_jitter_srodka_pct": mediana_jitter_srodka_pct,
        "mediana_ruch_srodka_pct": mediana_ruch_srodka_pct,
        "profil": profil,
        "odcinki": odcinki,
        "srodek": srodek,
        "brzegi": brzegi,
        "pary_niepewne": pary_niepewne,
        "klasa": klasa,
        "zrodlo": "lk_ransac_affine",
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
    if "shaky" in (ruch.get("klasa") or []):
        flagi.append("trzesie")
    return flagi
