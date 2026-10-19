"""Logika CLI: raport zdjecia (foto/image), ten sam silnik i szkielet raportu co
klipy - patrz kontrakt sesji "raport ujecia dla ZDJEC i ASSETOW" (wersja_metryk
"0.2", 2026-09-12). Wywolywane przez `python -m eyes photo` (eyes/cli.py) i
przez eyes/cmd_batch.py (--rodzaj foto).

photo --project "Nazwa" --files <plik1> <plik2> ...
      [--out X] [--config X] [--force]

Dekodowanie: Pillow (`ImageOps.exif_transpose` dla orientacji EXIF).
RAF bez JPG obok w tym samym folderze: JPEG wbudowany wyjety z naglowka RAF
(offset+dlugosc big-endian w bajtach 84..92 - sprawdzone na X-T4). HEIC/DNG:
brak dekodera w tym repo (Pillow bez wtyczki RAW/HEIF, `pip install`
zakazane) - plik jest POMIJANY z wpisem w logu, nie liczy sie jako blad.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import datetime
import io
import math
import platform
import re
import struct
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

from eyes import cmd_measure as measure_mod  # noqa: E402
from eyes import keys as keys_mod  # noqa: E402
from eyes import metrics as metrics_mod  # noqa: E402
from eyes import report as report_mod  # noqa: E402
from eyes import scopes as scopes_mod  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402

# Progi foto - PROWIZORYCZNE (jak PROGI_PROWIZORYCZNE wideo w eyes/metrics.py).
# lapvar_nieostre_max: skala pomiaru 960 px (dluzszy bok). Kalibracja
# 2026-09-12 na folderze jednego dnia zdjeciowego,
# pierwsze 20 JPG posortowanych po nazwie, lapvar liczony jak ostrosc.lapvar
# ale na calej klatce (bez podzialu 3x3) w skali 960. Skrajnosci sortowania
# (3 najnizsze: DSCF1150 87, DSCF1067 99, DSCF0997 134; 3 najwyzsze: DSCF1050
# 1963, DSCF1104 2016, DSCF1093 1645) OBEJRZANE - "niskie" wcale nie sa
# wyraznie nieostre (wschod slonca nad chmurami z niskim kontrastem, makro
# kwiatu z ostrym pierwszym planem ale rozmytym tlem bokeh, portret z
# rozmytym pierwszym planem) - lapvar tu low bo tresc ma malo faktury/
# kontrastu, nie bo jest nieostre (patrz docs/report-fields.md, ta sama
# pulapka co przy wideo). Fallback z kontraktu: prog = 1/3 mediany 20 probek
# (mediana 553.9 -> prog 184.6).
PROGI_FOTO = {
    "clip_hi_pct_max": 1.0,
    "p5_czern_mleczna_max": 0.06,
    "p1_czern_zabita_max": 0.005,
    "clip_lo_pct_czern_zabita_min": 2.0,
    "lapvar_nieostre_max": 184.6,
    "iso_wysokie_min": 3200,
    # NIE skalibrowane (kontrakt nie wymagal kalibracji tego progu, tylko
    # lapvar) - wartosc robocza jak PROGI_PROWIZORYCZNE wideo na starcie.
    "sigma_szum_max": 0.02,
}

SUPPORTED_DIRECT_EXTS = {"jpg", "jpeg", "png", "tif", "tiff", "webp"}
NO_DECODER_EXTS = {"heic", "dng"}

# Rozszerzenia trzymane w indeksie wariantow (warianty.jpg/raf/ig/xmp).
WARIANT_EXTS = ("jpg", "jpeg", "raf", "xmp")

_RE_CRS_LOOK = re.compile(r"<crs:Look>(.*?)</crs:Look>", re.DOTALL)
_RE_CRS_NAME = re.compile(r'crs:Name="([^"]*)"')
_RE_CRS_ATTR = re.compile(r'crs:([A-Za-z0-9]+)="([^"]*)"')
# forma elementowa: <crs:Exposure2012>+0.50</crs:Exposure2012> (Lightroom pisze
# skalary jako atrybuty, ale XMP dopuszcza oba zapisy). [^<>]* nie wejdzie w
# bloki zlozone (<crs:ToneCurvePV2012><rdf:Seq>...), wiec listy zostaja pominiete.
_RE_CRS_ELEM = re.compile(r"<crs:([A-Za-z0-9]+)>([^<>]*)</crs:\1>")


class NoDecoderError(Exception):
    def __init__(self, ext: str) -> None:
        self.ext = ext
        super().__init__(f"brak dekodera dla .{ext} (Pillow bez wtyczki, pip install zakazane)")


def _str_tag(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="replace")
    s = str(val).strip().rstrip("\x00").strip()
    return s or None


def _rational(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _read_exif(im: Image.Image) -> dict:
    empty = {
        "aparat": None, "obiektyw": None, "ogniskowa_mm": None, "ogniskowa_35mm": None,
        "przyslona": None, "czas_naswietlania": None, "czas_naswietlania_s": None,
        "iso": None, "ev": None, "wb": None, "data": None, "orientacja": None,
    }
    try:
        exif = im.getexif()
    except Exception:
        return empty
    if not exif or len(exif) == 0:
        return empty

    out = dict(empty)
    out["aparat"] = _str_tag(exif.get(0x0110))
    orient = exif.get(0x0112)
    out["orientacja"] = int(orient) if orient is not None else None

    try:
        exif_ifd = exif.get_ifd(0x8769) or {}
    except Exception:
        exif_ifd = {}

    out["obiektyw"] = _str_tag(exif_ifd.get(0xA434))
    out["ogniskowa_mm"] = _rational(exif_ifd.get(0x920A))
    fl35 = exif_ifd.get(0xA405)
    out["ogniskowa_35mm"] = int(fl35) if fl35 is not None else None
    out["przyslona"] = _rational(exif_ifd.get(0x829D))

    et = _rational(exif_ifd.get(0x829A))
    if et is not None and et > 0:
        out["czas_naswietlania_s"] = et
        out["czas_naswietlania"] = f"1/{round(1 / et)}" if et < 1 else f"{et:g}s"

    iso_raw = exif_ifd.get(0x8827)
    if iso_raw is not None:
        try:
            out["iso"] = int(iso_raw[0]) if isinstance(iso_raw, (tuple, list)) else int(iso_raw)
        except (TypeError, ValueError, IndexError):
            out["iso"] = None

    out["ev"] = _rational(exif_ifd.get(0x9204))

    wb = exif_ifd.get(0xA403)
    if wb == 0:
        out["wb"] = "auto"
    elif wb == 1:
        out["wb"] = "reczny"

    dt = _str_tag(exif_ifd.get(0x9003))
    if dt and len(dt) >= 19 and dt[4] == ":" and dt[7] == ":":
        out["data"] = f"{dt[:4]}-{dt[5:7]}-{dt[8:]}"
    elif dt:
        out["data"] = dt

    return out


def _proporcje(w: int, h: int) -> str:
    g = math.gcd(w, h) or 1
    return f"{w // g}:{h // g}"


def _orientacja_kadru(w: int, h: int) -> str:
    if w > h:
        return "poziom"
    if h > w:
        return "pion"
    return "kwadrat"


def _entropy_u8(gray: np.ndarray) -> float:
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = int(hist.sum())
    if total <= 0:
        return 0.0
    p = hist[hist > 0].astype(np.float64) / total
    return float(-np.sum(p * np.log2(p)))


def _coerce_num(v: str):
    try:
        f = float(v)
    except ValueError:
        return v
    return f if math.isfinite(f) else v


def _parse_xmp_crs(path: Path) -> dict:
    """Atrybuty crs:* z XMP Lightrooma - regex (bez nowych pakietow, patrz
    modul docstring kontraktu). `crs:Look` jest blokiem ZAGNIEZDZONYM (wlasne
    rdf:Description z crs:Name...) - wycinany z tekstu PRZED zbieraniem
    plaskich atrybutow najwyzszego poziomu, a jego crs:Name trafia do klucza
    "Look" osobno."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    look_name = None
    m = _RE_CRS_LOOK.search(text)
    if m:
        nm = _RE_CRS_NAME.search(m.group(1))
        if nm:
            look_name = nm.group(1)
        text = text[: m.start()] + text[m.end():]

    flat: dict = {}
    for key, val in _RE_CRS_ATTR.findall(text):
        flat[key] = _coerce_num(val)
    for key, val in _RE_CRS_ELEM.findall(text):
        val = val.strip()
        if val and key not in flat:  # atrybut ma pierwszenstwo (ten sam klucz dwa razy = ten sam XMP)
            flat[key] = _coerce_num(val)
    if look_name is not None:
        flat["Look"] = look_name
    return flat


def zbuduj_indeks_wariantow(roots) -> dict[tuple[str, str], list[Path]]:
    """Indeks {(stem malymi, ext): [sciezki]} z REKURENCYJNEGO obejscia
    folderow przemialu - budowany RAZ na batch (patrz cmd_batch --rodzaj
    foto/assets, ktory podaje --warianty-root). Bez niego warianty lezace w
    innym folderze niz plik bazowy nigdy nie zostaja znalezione: typowo JPG-i
    siedza w folderze dnia (`Dzien N/`), a wersje `_IG` w osobnym folderze
    obrobionych, wiec `warianty.ig` bylo zawsze null."""
    idx: dict[tuple[str, str], list[Path]] = {}
    for r in roots or []:
        root = Path(r)
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            stem, ext = keys_mod.split_base_ext(p.name)
            if ext in WARIANT_EXTS:
                idx.setdefault((stem.lower(), ext), []).append(p)
    for lista in idx.values():
        lista.sort(key=lambda x: str(x).replace("\\", "/").lower())
    return idx


def _find_variant(folder: Path, stem: str, exts: tuple[str, ...], index=None) -> Path | None:
    """Szuka {stem}.{ext} NAJPIERW obok pliku bazowego (Windows: dopasowanie
    bez wzgledu na wielkosc liter dzieki NTFS, wiec jeden Path.exists() na
    wariant wystarcza), a dopiero potem - gdy podano indeks przemialu
    (zbuduj_indeks_wariantow) - w calym drzewie folderow batcha. Kolejnosc jest
    wazna: lokalny wariant wygrywa z jakimkolwiek innym o tym samym stemie."""
    for ext in exts:
        p = folder / f"{stem}.{ext}"
        if p.exists():
            return p
    if index:
        for ext in exts:
            kandydaci = index.get((stem.lower(), ext))
            if kandydaci:
                return kandydaci[0]
    return None


def _raf_embedded_jpeg_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        head = f.read(100)
        if len(head) < 92:
            raise RuntimeError(f"RAF za krotki, brak naglowka: {path}")
        offset, length = struct.unpack(">II", head[84:92])
        f.seek(offset)
        data = f.read(length)
    if data[:2] != b"\xff\xd8":
        raise RuntimeError(f"RAF: wbudowany JPEG nie zaczyna sie od SOI (offset={offset}): {path}")
    return data


def _open_image(path: Path) -> tuple[Image.Image, str]:
    """Zwraca (obraz Pillow PRZED exif_transpose, plik_pomiaru wg kontraktu).
    Rzuca NoDecoderError dla HEIC/DNG (zlapane przez wywolujacego -> pominiete,
    nie blad)."""
    ext = path.suffix.lower().lstrip(".")
    if ext == "raf":
        jpg_sibling = _find_variant(path.parent, path.stem, ("jpg", "jpeg"))
        if jpg_sibling is not None:
            im = Image.open(jpg_sibling)
            im.load()
            return im, str(jpg_sibling.resolve()).replace("\\", "/")
        data = _raf_embedded_jpeg_bytes(path)
        im = Image.open(io.BytesIO(data))
        im.load()
        return im, str(path.resolve()).replace("\\", "/") + "#embedded"
    if ext in NO_DECODER_EXTS:
        raise NoDecoderError(ext)
    im = Image.open(path)
    im.load()
    return im, str(path.resolve()).replace("\\", "/")


def _resize_longer(im: Image.Image, target: int) -> Image.Image:
    """Skaluje tak, zeby DLUZSZY bok = target; nigdy nie powieksza (obraz
    mniejszy niz target zostaje bez zmian)."""
    w, h = im.size
    longer = max(w, h)
    if longer <= target:
        return im.copy()
    scale = target / longer
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    return im.resize((new_w, new_h), Image.LANCZOS)


def _save_resized_jpeg(im: Image.Image, path: Path, target: int, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _resize_longer(im, target).convert("RGB").save(path, "JPEG", quality=quality)


def compute_flagi_foto(tonalnosc: dict, ostrosc: dict, szum: dict, exif: dict, progi: dict) -> list[str]:
    flagi = []
    if tonalnosc["clip_hi_pct"] > progi["clip_hi_pct_max"]:
        flagi.append("clip_hi>1%")
    if tonalnosc["p5"] > progi["p5_czern_mleczna_max"]:
        flagi.append("czern_mleczna")
    if (tonalnosc["p1"] < progi["p1_czern_zabita_max"]
            and tonalnosc["clip_lo_pct"] > progi["clip_lo_pct_czern_zabita_min"]):
        flagi.append("czern_zabita")
    if ostrosc["lapvar"] < progi["lapvar_nieostre_max"]:
        flagi.append("nieostre")
    iso = (exif or {}).get("iso")
    if iso is not None and iso > progi["iso_wysokie_min"]:
        flagi.append("iso_wysokie")
    sigma = (szum or {}).get("sigma")
    if sigma is not None and sigma > progi["sigma_szum_max"]:
        flagi.append("szum")
    return flagi


def measure_photo(
    path: Path, *, project: str, cfg, force: bool = False,
    hash_by_path: dict, file_paths: list[Path], rodzaj: str = "photo",
    variant_index=None,
) -> dict:
    """Mierzy jedno zdjecie/obraz. Zwraca dict do zalogowania (id, plik,
    status, czas_calkowity_s, raport) - jak cmd_measure.process_file.
    `rodzaj`: "photo" (batch foto, EXIF oczekiwany) albo "image" (batch
    assets - EXIF moze brakowac, to nie jest blad, patrz _read_exif).
    Rzuca wyjatek przy prawdziwym bledzie; brak dekodera (HEIC/DNG) NIE
    rzuca - zwraca status "pominieto" z powodem w polu "powod"."""
    cache_root = Path(cfg.cache_root)
    id_ = keys_mod.compute_id(path, file_paths)
    report_dir = cfg.reports_dir(project)
    report_path = report_dir / f"{id_}.json"

    if report_path.exists() and not force:
        print(f"{id_}: raport juz istnieje, pomijam (--force wymusza ponowny pomiar)")
        return {"id": id_, "plik": path.name, "status": "pominieto", "czas_calkowity_s": None, "raport": str(report_path)}

    t0 = time.perf_counter()

    try:
        im_raw, plik_pomiaru = _open_image(path)
    except NoDecoderError as e:
        print(f"{id_}: pominieto, brak dekodera dla .{e.ext}")
        return {
            "id": id_, "plik": path.name, "status": "pominieto",
            "powod": "brak_dekodera", "czas_calkowity_s": None, "raport": None,
        }

    exif = _read_exif(im_raw)
    im = ImageOps.exif_transpose(im_raw)
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size

    small = _resize_longer(im, 960)
    arr960 = np.asarray(small)
    frame = arr960[np.newaxis, ...]

    tonalnosc = metrics_mod.compute_tonalnosc(frame)
    y = metrics_mod.to_luma709(frame)[0]
    hist64, _ = np.histogram(y.reshape(-1), bins=64, range=(0.0, 1.0))
    total64 = int(hist64.sum())
    tonalnosc["histogram_64"] = (hist64 / total64).tolist() if total64 > 0 else [0.0] * 64

    kolor = metrics_mod.compute_kolor(frame)
    ostrosc, _idx_sharp = metrics_mod.compute_ostrosc(frame)
    ostrosc["skala_pomiaru_px"] = 960
    ostrosc["fokus_komorka"] = int(np.argmax(ostrosc["siatka_3x3"]))
    szum = metrics_mod.compute_szum(frame[0])

    gray960 = cv2.cvtColor(arr960, cv2.COLOR_RGB2GRAY)
    entropia = _entropy_u8(gray960)

    proporcje = _proporcje(w, h)
    kadr = {
        "w": w, "h": h,
        "mpx": round(w * h / 1_000_000, 1),
        "proporcje": proporcje,
        "orientacja": _orientacja_kadru(w, h),
        "entropia": round(entropia, 3),
    }

    folder = path.parent
    stem = path.stem
    jpg_var = _find_variant(folder, stem, ("jpg", "jpeg"), variant_index)
    raf_var = _find_variant(folder, stem, ("raf",), variant_index)
    xmp_var = _find_variant(folder, stem, ("xmp",), variant_index)
    ig_var = _find_variant(folder, f"{stem}_IG", ("jpg", "jpeg"), variant_index)

    warianty: dict = {"jpg": jpg_var is not None, "raf": raf_var is not None, "ig": None, "xmp": None}
    if ig_var is not None:
        try:
            im_ig = ImageOps.exif_transpose(Image.open(ig_var))
            iw, ih = im_ig.size
            ig_prop = _proporcje(iw, ih)
            warianty["ig"] = {
                "plik": str(ig_var.resolve()).replace("\\", "/"),
                "w": iw, "h": ih, "proporcje": ig_prop,
                "rozmiar_b": ig_var.stat().st_size,
                "crop": ig_prop != proporcje,
            }
        except Exception:
            warianty["ig"] = None
    if xmp_var is not None:
        warianty["xmp"] = {"plik": str(xmp_var.resolve()).replace("\\", "/"), "crs": _parse_xmp_crs(xmp_var)}

    id_cache_dir = cache_root / project / id_
    frames_dir = id_cache_dir / "frames"
    scopes_dir = id_cache_dir / "scopes"

    podglad_path = frames_dir / f"{id_}_podglad.jpg"
    kafel_path = frames_dir / f"{id_}_kafel.jpg"
    _save_resized_jpeg(im, podglad_path, 1920, quality=90)
    _save_resized_jpeg(im, kafel_path, 640, quality=75)

    def rel(p: Path) -> str:
        return measure_mod.rel_to(p, cache_root)

    klatki = [
        {"rola": "pierwsza", "plik": rel(podglad_path)},
        {"rola": "najostrzejsza", "plik": rel(podglad_path)},
        {"rola": "kafel", "plik": rel(kafel_path)},
    ]

    skopy = []
    for typ, ffilter in (
        ("waveform", "waveform"),
        ("parade", "waveform=mode=column:components=7"),
        ("vectorscope", "vectorscope"),
        ("histogram", "histogram=display_mode=stack"),
    ):
        out_p = scopes_dir / f"{id_}_{typ}.png"
        scopes_mod.render_scope_still(str(podglad_path), ffilter, out_p, max_width=1024)
        skopy.append({"typ": typ, "plik": rel(out_p)})

    flagi = compute_flagi_foto(tonalnosc, ostrosc, szum, exif, PROGI_FOTO)

    stat = path.stat()
    kamera = exif.get("aparat") or "nieznana"
    zrodlo = {
        "plik": path.name,
        "sciezka_rel": str(path.resolve()).replace("\\", "/"),
        "hash_4mb": hash_by_path[path],
        "rozmiar_b": stat.st_size,
        "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "kamera": kamera,
        "profil": None,
        "lut_pomiarowy": None,
        "czas_s": None,
        "rodzaj": rodzaj,
        "plik_pomiaru": plik_pomiaru,
    }
    stream = {
        "codec": (im_raw.format or "").lower() or None,
        "w": w, "h": h,
        "fps": None, "fps_avg": None,
        "pix_fmt": (im.mode or "").lower() or None,
        "range": None, "transfer": None, "primaries": None,
        "nb_frames": None,
    }
    okno_pomiaru = {"tryb": "still"}
    ruch = {"klasa": [], "metoda": None}
    plynnosc: dict = {}
    montaz = {"segmenty": []}
    niepewnosc = {
        "pomiar_bez_lut": False,
        "kamera_nieznana": bool(kamera == "nieznana"),
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
        "opencv": cv2.__version__,
        "host": platform.node(),
    }

    report = report_mod.build_report(
        id_=id_, projekt=project, zrodlo=zrodlo, stream=stream, okno_pomiaru=okno_pomiaru,
        tonalnosc=tonalnosc, kolor=kolor, ostrosc=ostrosc, szum=szum, ruch=ruch,
        plynnosc=plynnosc, montaz=montaz, klatki=klatki, skopy=skopy,
        flagi=flagi, progi=PROGI_FOTO, niepewnosc=niepewnosc, pomiar=pomiar,
        exif=exif, kadr=kadr, warianty=warianty,
    )
    report_mod.write_report(report, report_path)

    print(f"{id_}: kamera={kamera} rodzaj={rodzaj} calkowity={t_total:.2f}s raport={report_path}")
    return {"id": id_, "plik": path.name, "status": "ok", "czas_calkowity_s": round(t_total, 3), "raport": str(report_path)}


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Raport zdjecia v0 (sonny-eyes)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--warianty-root", dest="warianty_root", nargs="*", default=None,
        help="foldery przemialu do rekurencyjnego szukania wariantow (_IG/RAF/XMP lezacych "
        "w innym folderze niz plik bazowy); podaje je cmd_batch, indeks liczony raz na batch",
    )
    ap.add_argument("--cache-root", default=None, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None, on_progress=None) -> int:
    """on_progress(entry) - jak cmd_measure.main; woluje go eyes.cmd_batch
    (--rodzaj foto) do _postep.json."""
    args = parse_args(argv)
    overrides = overrides_from_out(args.out or args.cache_root)
    cfg = load_config(args.config, overrides=overrides)
    file_paths = [Path(f).resolve() if Path(f).exists() else Path(f) for f in args.files]

    hash_by_path = {p: keys_mod.hash_4mb(p) for p in file_paths}
    dup_map = keys_mod.find_duplicate_hashes(file_paths)
    unique_paths = [p for p in file_paths if p not in dup_map]

    project_cache = Path(cfg.cache_root) / args.project
    log_path = project_cache / "_log.jsonl"

    # jedno obejscie drzewa na caly przemial (nie na plik)
    variant_index = zbuduj_indeks_wariantow(args.warianty_root) if args.warianty_root else None

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
            result = measure_photo(
                path, project=args.project, cfg=cfg, force=args.force,
                hash_by_path=hash_by_path, file_paths=unique_paths,
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
