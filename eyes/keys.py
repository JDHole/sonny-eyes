"""Identyfikacja plikow: klucz v1 (specyfikacja Dextera, raport "Shadow notes - nastepca" 2026-09-05, sekcja 8),
hash_4mb i rozpoznanie kamery.

Jedna specyfikacja, dwie implementacje: JS w media_store.js (silnik vaulta) i ten port. Zgodnosc pilnuja wektory
testowe w tests/test_keys.py (te same, co u Dextera).

Regula:
1. Wejscie: sciezka WZGLEDNA od korzenia projektu (ukosniki /). base = nazwa bez ostatniego rozszerzenia,
   ext = rozszerzenie malymi literami.
2. Sufiks wersji: gdy base konczy sie sufiksem z variant_suffixes (domyslnie tylko "_IG", bez wielkosci liter),
   sufiks jest obcinany, a plik trafia do wariantu "ig". Inne koncowki (-V1, _export, _final) zostaja w nazwie.
3. id = base po obcieciu, z zachowaniem wielkosci liter z pliku. Rownosc id jest BEZ wielkosci liter.
4. Warianty: ten sam id, inne rozszerzenie lub sufiks = ten sam rekord; klucz wariantu = "ig" dla sufiksu _IG,
   inaczej rozszerzenie (jpg, raf, xmp, mov, mp4, wav, png ...).
5. Kolizja: ten sam id (ci) i ten sam wariant w innym folderze = inne ujecie. Pierwszy po posortowaniu sciezek
   wzglednych (porownanie po kodach znakow, nie locale) zachowuje id, kazdy nastepny dostaje "id@folder",
   folder = nazwa bezposredniego folderu nadrzednego.
6. Zakres unikalnosci: projekt. Poza projektem id kwalifikuje sie nazwa projektu: "Projekt/ID" (qualified()).
7. Znaki: id zawiera tylko znaki z nazwy pliku i "@"; nigdy "#", "/", "\\". Nazwa raportu = "{id}.json".

Uwaga v0: nie ma trwalego indeksu, wiec gwarancje "raz nadany id nie zmienia sie" da dopiero indeks Dextera (faza 2);
do tego czasu id liczy sie per uruchomienie z podanej listy plikow.
Ponad specyfikacje (zgloszone Dexterowi): (a) identyczny hash_4mb = duplikat tresci, mierzony raz, NIE kolizja,
dlatego kolizje licz na liscie PO dedupie; (b) gdy "id@folder" jest juz zajete (dwa foldery nadrzedne o tej samej
nazwie, np. 100_FUJI i DCIM/100_FUJI), dopisuje "~2", "~3" i zwraca ostrzezenie.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

HASH_BYTES = 4 * 1024 * 1024
DEFAULT_VARIANT_SUFFIXES: tuple[str, ...] = ("_IG",)
FORBIDDEN_CHARS = set("#/\\")


def hash_4mb(path: Path | str) -> str:
    """sha1 hex pierwszych 4 MB pliku (ten sam algorytm ma miec import v2 Dextera)."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read(HASH_BYTES))
    return h.hexdigest()


@dataclass(frozen=True)
class KeyInfo:
    rel_path: str          # sciezka wzgledna, ukosniki /
    id: str                # klucz rekordu (wielkosc liter z pliku)
    variant: str           # ig / jpg / raf / mov / mp4 / wav / png / xmp ...
    folder: str            # bezposredni folder nadrzedny ("" gdy plik w korzeniu)
    collision: bool        # True gdy id dostal sufiks @folder
    warning: str | None    # ostrzezenie ponad spec (np. folder o tej samej nazwie)


def norm_rel(rel: str | Path) -> str:
    s = str(rel).replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s.lstrip("/")


def split_base_ext(filename: str) -> tuple[str, str]:
    """base bez OSTATNIEGO rozszerzenia, ext malymi literami (bez kropki)."""
    i = filename.rfind(".")
    if i > 0:
        return filename[:i], filename[i + 1:].lower()
    return filename, ""


def strip_variant(base: str, suffixes: tuple[str, ...] = DEFAULT_VARIANT_SUFFIXES) -> tuple[str, str | None]:
    """Obcina sufiks wersji (bez wielkosci liter). Zwraca (base_po_obcieciu, klucz_wariantu | None)."""
    low = base.lower()
    for suf in suffixes:
        s = suf.lower()
        if len(base) > len(s) and low.endswith(s):
            return base[: -len(s)], s.lstrip("_-").lower()  # "_IG" -> "ig"
    return base, None


def assign_ids(rel_paths, variant_suffixes: tuple[str, ...] = DEFAULT_VARIANT_SUFFIXES) -> dict[str, KeyInfo]:
    """Nadaje id wszystkim sciezkom (wzglednym od korzenia projektu). Lista powinna byc PO dedupie po hashu."""
    paths = sorted({norm_rel(p) for p in rel_paths})  # kolejnosc = porownanie po kodach znakow
    parsed: list[tuple[str, str, str, str]] = []  # (rel, base, variant, folder)
    for rel in paths:
        filename = rel.rsplit("/", 1)[-1]
        folder = rel.rsplit("/", 1)[0].rsplit("/", 1)[-1] if "/" in rel else ""
        base, ext = split_base_ext(filename)
        base2, var = strip_variant(base, variant_suffixes)
        parsed.append((rel, base2, var or ext, folder))

    # grupy kolizyjne: ten sam id (ci) + ten sam wariant; kolejnosc w grupie = kolejnosc posortowanych sciezek
    groups: dict[tuple[str, str], list[tuple[str, str, str, str]]] = {}
    for item in parsed:
        groups.setdefault((item[1].lower(), item[2]), []).append(item)

    out: dict[str, KeyInfo] = {}
    for items in groups.values():
        taken: set[str] = set()
        for n, (rel, base, var, folder) in enumerate(items):
            if n == 0:
                id_, coll, warn = base, False, None
            else:
                id_, coll, warn = f"{base}@{folder}", True, None
                k = 2
                while id_.lower() in taken:
                    id_ = f"{base}@{folder}~{k}"
                    warn = f"kolizja w folderach o tej samej nazwie ({folder}); sufiks ~{k} ponad specyfikacje"
                    k += 1
            if any(ch in FORBIDDEN_CHARS for ch in id_):
                raise ValueError(f"niedozwolony znak w id: {id_!r} (z {rel})")
            taken.add(id_.lower())
            out[rel] = KeyInfo(rel_path=rel, id=id_, variant=var, folder=folder, collision=coll, warning=warn)
    return out


def qualified(project: str, id_: str) -> str:
    """Adres poza projektem: 'Projekt/ID'."""
    return f"{project}/{id_}"


def _common_root(paths: list[Path]) -> Path:
    parts = [p.resolve().parts for p in paths]
    common = parts[0]
    for q in parts[1:]:
        n = 0
        while n < min(len(common), len(q)) and common[n].lower() == q[n].lower():
            n += 1
        common = common[:n]
    return Path(*common) if common else Path(paths[0].anchor)


def _rel(p: Path, base: Path) -> str:
    try:
        return norm_rel(Path(p).resolve().relative_to(base.resolve()))
    except ValueError:
        return norm_rel(Path(p).name)


def compute_id(path: Path, all_paths: list[Path], root: Path | None = None) -> str:
    """Zgodnosciowo dla measure.py: id dla `path` w kontekscie `all_paths` (lista PO dedupie po hashu).
    Sciezki wzgledne liczone od `root` (domyslnie: wspolny korzen listy)."""
    paths = list(all_paths)
    if path not in paths:
        paths.append(path)
    base = Path(root) if root else _common_root(paths)
    info = assign_ids([_rel(p, base) for p in paths])
    return info[_rel(path, base)].id


def find_duplicate_hashes(paths: list[Path]) -> dict[Path, Path]:
    """Mapa path -> oryginal dla plikow o identycznym hash_4mb jak wczesniejszy plik na liscie (duplikat tresci)."""
    seen: dict[str, Path] = {}
    dup_of: dict[Path, Path] = {}
    for p in paths:
        h = hash_4mb(p)
        if h in seen:
            dup_of[p] = seen[h]
        else:
            seen[h] = p
    return dup_of


_RE_FUJI = re.compile(r"^DSCF.*\.MOV$", re.IGNORECASE)
_RE_GOPRO = re.compile(r"^(GX|GH|GOPR).*\.MP4$", re.IGNORECASE)

PROFIL_PO_KAMERZE = {"Fuji": "F-Log", "GoPro": "Rec709"}


def detect_camera(filename: str) -> tuple[str, bool]:
    """(kamera, kamera_nieznana): DSCF*.MOV -> Fuji; GX/GH/GOPR*.MP4 -> GoPro; inne -> nieznana."""
    if _RE_FUJI.match(filename):
        return "Fuji", False
    if _RE_GOPRO.match(filename):
        return "GoPro", False
    return "nieznana", True
