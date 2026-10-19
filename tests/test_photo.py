"""Test dymny modulu foto (bramka). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_photo.py

Mierzy 1 JPG (PHOTO_JPG_WITH_RAF, z siostrzanym RAF+XMP) i 1 RAF-only
(PHOTO_RAF_ONLY, bez JPG obok - embedded JPEG wyjety z naglowka RAF; sciezki
z tests/_material.py, brak = SKIP) do TYMCZASOWEGO --out
(NIE do prawdziwego cache/reports), sprawdza komplet kluczy najwyzszego
poziomu (w tym exif/kadr/warianty), zakresy 0..1, monotonicznosc percentyli,
histogram_64 (suma ~1), obecnosc i rozmiar plikow PNG/JPG, exif.aparat dla
Fuji. Osobno (bez pomiaru, sama logika): parowanie JPG+RAF i pomijanie
_IG/_stock/_export w eyes.cmd_batch.zbierz_foto, na pustych plikach.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_batch  # noqa: E402
from eyes import cmd_photo  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402

from _material import material, skip_reason  # noqa: E402

JPG_Z_RAF = material("PHOTO_JPG_WITH_RAF")
RAF_SAM = material("PHOTO_RAF_ONLY")

TOP_KEYS = [
    "wersja_metryk", "id", "projekt", "zrodlo", "stream", "okno_pomiaru",
    "tonalnosc", "kolor", "ostrosc", "szum", "ruch", "plynnosc", "montaz",
    "klatki", "skopy", "flagi_prowizoryczne", "progi_prowizoryczne",
    "werdykty", "niepewnosc", "pomiar", "exif", "kadr", "warianty",
]

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def zmierz_i_sprawdz(path: Path, cfg, project: str, oczekiwana_kamera: str | None) -> dict | None:
    hash_by_path = {path.resolve(): "test-hash"}
    r = cmd_photo.measure_photo(
        path.resolve(), project=project, cfg=cfg, force=True,
        hash_by_path=hash_by_path, file_paths=[path.resolve()],
    )
    check(r["status"] == "ok", f"{path.name}: status={r['status']} (oczekiwano ok)")
    if r["status"] != "ok":
        return None

    report_path = Path(r["raport"])
    check(report_path.exists(), f"{path.name}: brak pliku raportu {report_path}")
    if not report_path.exists():
        return None
    data = json.loads(report_path.read_text(encoding="utf-8"))

    for key in TOP_KEYS:
        check(key in data, f"{path.name}: brak klucza najwyzszego poziomu '{key}'")

    tonalnosc = data.get("tonalnosc", {})
    percentile_keys = ["p1", "p5", "p50", "p95", "p99"]
    values = {}
    for pk in percentile_keys:
        v = tonalnosc.get(pk)
        values[pk] = v
        check(v is not None and 0.0 <= v <= 1.0, f"{path.name}: tonalnosc.{pk}={v} poza zakresem 0..1")
    if all(values[pk] is not None for pk in percentile_keys):
        check(
            values["p1"] <= values["p5"] <= values["p50"] <= values["p95"] <= values["p99"],
            f"{path.name}: percentyle nie rosna monotonicznie: {values}",
        )

    hist = tonalnosc.get("histogram_64")
    check(isinstance(hist, list) and len(hist) == 64, f"{path.name}: histogram_64 nie ma 64 kubelkow ({hist and len(hist)})")
    if isinstance(hist, list) and hist:
        total = sum(hist)
        # Raport zaokragla KAZDY float do 3 miejsc (eyes/report.py:round_floats,
        # ta sama regula co reszta raportu) - suma 64 zaokraglonych kubelkow
        # moze odjechac od 1.0 troche wiecej niz kontraktowe "1+-0.001" liczone
        # na wartosciach SPRZED zaokraglenia (zmierzone: do 1.002). 0.004 to
        # bezpieczny margines na ten efekt zaokraglenia, nie zmiana kontraktu.
        check(abs(total - 1.0) <= 0.004, f"{path.name}: histogram_64 sumuje sie do {total}, oczekiwano 1+-0.004 (po zaokragleniu raportu)")

    ostrosc = data.get("ostrosc", {})
    check(ostrosc.get("skala_pomiaru_px") == 960, f"{path.name}: ostrosc.skala_pomiaru_px={ostrosc.get('skala_pomiaru_px')} oczekiwano 960")
    fokus = ostrosc.get("fokus_komorka")
    check(isinstance(fokus, int) and 0 <= fokus <= 8, f"{path.name}: ostrosc.fokus_komorka={fokus} poza 0..8")

    szum = data.get("szum", {})
    check("sigma" in szum, f"{path.name}: szum bez klucza sigma")

    cache_root = Path(cfg.cache_root)
    for fr in data.get("klatki", []):
        p = cache_root / fr["plik"]
        check(p.exists(), f"{path.name}: brak pliku klatki {p}")
        if p.exists():
            check(p.stat().st_size > 0, f"{path.name}: {p} ma 0 B")
    skopy = data.get("skopy", [])
    check(len(skopy) == 4, f"{path.name}: oczekiwano 4 skopy (waveform/parade/vectorscope/histogram), jest {len(skopy)}")
    for sc in skopy:
        p = cache_root / sc["plik"]
        check(p.exists(), f"{path.name}: brak pliku skopu {p}")
        if p.exists():
            check(p.stat().st_size > 0, f"{path.name}: {p} ma 0 B")

    if oczekiwana_kamera is not None:
        check(data["exif"].get("aparat") == oczekiwana_kamera, f"{path.name}: exif.aparat={data['exif'].get('aparat')!r} oczekiwano {oczekiwana_kamera!r}")

    kadr = data.get("kadr", {})
    check(isinstance(kadr.get("w"), int) and kadr["w"] > 0, f"{path.name}: kadr.w={kadr.get('w')}")
    check(isinstance(kadr.get("h"), int) and kadr["h"] > 0, f"{path.name}: kadr.h={kadr.get('h')}")
    check(kadr.get("orientacja") in ("poziom", "pion", "kwadrat"), f"{path.name}: kadr.orientacja={kadr.get('orientacja')}")

    return data


def test_parowanie_i_pomijanie(tmp_root: Path) -> None:
    """Logika eyes.cmd_batch.zbierz_foto: JPG+RAF tego samego stemu w tym
    samym folderze -> mierzony TYLKO JPG; RAF bez JPG -> RAF; warianty
    _IG/_stock/_export pominiete calkowicie z listy do pomiaru. Puste pliki -
    sprawdzana jest WYLACZNIE logika zbierania/parowania, bez dekodowania."""
    folder = tmp_root / "batch_logic"
    folder.mkdir(parents=True, exist_ok=True)
    nazwy = [
        "DSCF0001.JPG", "DSCF0001.RAF",  # para -> tylko JPG
        "DSCF0002.RAF",                  # RAF-only -> RAF
        "DSCF0003.JPG",                  # tylko JPG
        "DSCF0003_IG.jpg",               # wariant IG -> pominiety
        "DSCF0004_stock.png",            # wariant stock -> pominiety
        "DSCF0005_export.jpg",           # wariant export -> pominiety
        "notatka.txt",                   # spoza wzorcow foto -> pominiety
    ]
    for n in nazwy:
        (folder / n).write_bytes(b"")

    wynik = sorted(p.name for p in cmd_batch.zbierz_foto([str(folder)]))
    oczekiwane = sorted(["DSCF0001.JPG", "DSCF0002.RAF", "DSCF0003.JPG"])
    check(wynik == oczekiwane, f"zbierz_foto: {wynik} != {oczekiwane}")


def test_indeks_wariantow(tmp_root: Path) -> None:
    """Warianty spoza folderu pliku bazowego: typowo JPG-i leza w folderze
    dnia ("Dzien N"), a wersje _IG w osobnym folderze obrobionych, wiec
    samo Path.exists() obok pliku NIGDY ich nie znajdzie - musi je znalezc
    indeks przemialu (cmd_photo.zbuduj_indeks_wariantow z folderow batcha,
    podawany przez cmd_batch jako --warianty-root). Puste pliki: sprawdzana
    jest wylacznie logika szukania, bez dekodowania."""
    root = tmp_root / "warianty"
    (root / "Dzien 1").mkdir(parents=True, exist_ok=True)
    (root / "Obrobione").mkdir(parents=True, exist_ok=True)
    (root / "Dzien 1" / "DSCF9001.JPG").write_bytes(b"")
    (root / "Dzien 1" / "DSCF9001.RAF").write_bytes(b"")
    (root / "Obrobione" / "DSCF9001_IG.jpg").write_bytes(b"")

    idx = cmd_photo.zbuduj_indeks_wariantow([str(root)])
    baza = root / "Dzien 1"

    bez_indeksu = cmd_photo._find_variant(baza, "DSCF9001_IG", ("jpg", "jpeg"))
    check(bez_indeksu is None, f"_IG z innego folderu nie jest widoczny bez indeksu, a zwrocono {bez_indeksu}")

    z_indeksem = cmd_photo._find_variant(baza, "DSCF9001_IG", ("jpg", "jpeg"), idx)
    check(
        z_indeksem is not None and z_indeksem.name == "DSCF9001_IG.jpg",
        f"indeks nie znalazl _IG w Obrobione/: {z_indeksem}",
    )

    lokalny = cmd_photo._find_variant(baza, "DSCF9001", ("raf",), idx)
    check(lokalny == baza / "DSCF9001.RAF", f"wariant obok pliku ma miec pierwszenstwo, jest {lokalny}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="eyes_test_photo_") as tmp_s:
        tmp = Path(tmp_s)
        cfg = load_config(None, overrides=overrides_from_out(str(tmp / "out")))

        powod = skip_reason("PHOTO_JPG_WITH_RAF", JPG_Z_RAF)
        if powod:
            print(powod)
        else:
            zmierz_i_sprawdz(JPG_Z_RAF, cfg, "TestPhotoJpg", "X-T4")

        powod = skip_reason("PHOTO_RAF_ONLY", RAF_SAM)
        if powod:
            print(powod)
        else:
            dane_raf = zmierz_i_sprawdz(RAF_SAM, cfg, "TestPhotoRaf", "X-T4")
            if dane_raf is not None:
                check(
                    dane_raf["zrodlo"]["plik_pomiaru"].endswith("#embedded"),
                    f"RAF-only: plik_pomiaru={dane_raf['zrodlo']['plik_pomiaru']!r} nie konczy sie #embedded",
                )
                check(dane_raf["warianty"]["jpg"] is False, "RAF-only: warianty.jpg powinno byc False")
                check(dane_raf["warianty"]["raf"] is True, "RAF-only: warianty.raf powinno byc True")

        test_parowanie_i_pomijanie(tmp)
        test_indeks_wariantow(tmp)

    if failures:
        print(f"TEST_PHOTO: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_PHOTO: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
