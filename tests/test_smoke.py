"""Test dymny (bramka). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_smoke.py

Sprawdza raporty DSCF3236 (Fuji) i GX010042 (GoPro) w projekcie
"Canarian Tweety EP03": komplet kluczy najwyzszego poziomu, zakresy 0..1 i
monotonicznosc percentyli tonalnosci, obecnosc i rozmiar 4 PNG, oraz
zgodnosc kamera/LUT z oczekiwaniem.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes.config import load_config  # noqa: E402

PROJECT = "Canarian Tweety EP03"
CASES = [
    {"id": "DSCF3236", "kamera": "Fuji"},
    {"id": "GX010042", "kamera": "GoPro"},
]

TOP_KEYS = [
    "wersja_metryk", "id", "projekt", "zrodlo", "stream", "okno_pomiaru",
    "tonalnosc", "kolor", "ostrosc", "szum", "ruch", "plynnosc", "montaz",
    "klatki", "skopy", "flagi_prowizoryczne", "progi_prowizoryczne",
    "werdykty", "niepewnosc", "pomiar",
]

MAX_PNG_BYTES = 500 * 1024

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    cfg = load_config(REPO_ROOT / "config.toml")
    report_dir = Path(cfg.vault) / "40_Pracownie" / "Analog Studio" / "Projekty" / PROJECT / "Color" / "reports"
    cache_root = Path(cfg.cache_root)

    for case in CASES:
        id_ = case["id"]
        report_path = report_dir / f"{id_}.json"
        check(report_path.exists(), f"{id_}: brak raportu {report_path}")
        if not report_path.exists():
            continue

        data = json.loads(report_path.read_text(encoding="utf-8"))

        for key in TOP_KEYS:
            check(key in data, f"{id_}: brak klucza najwyzszego poziomu '{key}'")

        tonalnosc = data.get("tonalnosc", {})
        percentile_keys = ["p1", "p5", "p50", "p95", "p99"]
        values = {}
        for pk in percentile_keys:
            v = tonalnosc.get(pk)
            values[pk] = v
            check(v is not None and 0.0 <= v <= 1.0, f"{id_}: tonalnosc.{pk}={v} poza zakresem 0..1")
        if all(values[pk] is not None for pk in percentile_keys):
            check(
                values["p1"] <= values["p5"] <= values["p50"] <= values["p95"] <= values["p99"],
                f"{id_}: percentyle nie rosna monotonicznie: {values}",
            )

        for fr in data.get("klatki", []):
            p = cache_root / fr["plik"]
            check(p.exists(), f"{id_}: brak pliku klatki {p}")
            if p.exists():
                check(p.stat().st_size <= MAX_PNG_BYTES, f"{id_}: {p} > 500 KB ({p.stat().st_size} B)")

        for sc in data.get("skopy", []):
            p = cache_root / sc["plik"]
            check(p.exists(), f"{id_}: brak pliku skopu {p}")
            if p.exists():
                check(p.stat().st_size <= MAX_PNG_BYTES, f"{id_}: {p} > 500 KB ({p.stat().st_size} B)")

        zrodlo = data.get("zrodlo", {})
        check(zrodlo.get("kamera") == case["kamera"], f"{id_}: kamera={zrodlo.get('kamera')} oczekiwano {case['kamera']}")

        niepewnosc = data.get("niepewnosc", {})
        if case["kamera"] == "Fuji":
            check(zrodlo.get("lut_pomiarowy") is not None, f"{id_}: lut_pomiarowy powinien byc ustawiony dla Fuji")
            check(niepewnosc.get("pomiar_bez_lut") is False, f"{id_}: niepewnosc.pomiar_bez_lut powinno byc false dla Fuji")
        else:
            check(zrodlo.get("lut_pomiarowy") is None, f"{id_}: lut_pomiarowy powinien byc null dla {case['kamera']}")

        # --- ruch v0.2: sanity strukturalny nowych pol - TYLKO gdy raport
        # faktycznie deklaruje wersja_metryk 0.2 (starsze raporty w tym samym
        # folderze, jeszcze nie przeliczone, maja stary ksztalt ruch i to jest
        # ok - regeneracja jest osobna decyzja, nie czescia tego smoke testu).
        if data.get("wersja_metryk") == "0.2":
            ruch = data.get("ruch", {})
            check(ruch.get("zrodlo") == "lk_ransac_affine", f"{id_}: ruch.zrodlo={ruch.get('zrodlo')} oczekiwano lk_ransac_affine")
            klasa = ruch.get("klasa")
            check(isinstance(klasa, list) and len(klasa) > 0, f"{id_}: ruch.klasa={klasa} puste/nie-lista")
            profil = ruch.get("profil")
            check(isinstance(profil, list), f"{id_}: ruch.profil nie jest lista")
            for p in profil or []:
                check(isinstance(p.get("t_s"), int), f"{id_}: profil.t_s={p.get('t_s')} nie jest int")
                for k in ("ruch_pct", "jitter_pct"):
                    v = p.get(k)
                    check(v is None or (isinstance(v, (int, float)) and v >= 0), f"{id_}: profil.{k}={v} poza zakresem (t_s={p.get('t_s')})")
                conf = p.get("conf")
                check(isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0, f"{id_}: profil.conf={conf} poza 0..1 (t_s={p.get('t_s')})")
            odcinki = ruch.get("odcinki")
            check(isinstance(odcinki, list), f"{id_}: ruch.odcinki nie jest lista")
            for o in odcinki or []:
                check(o.get("typ") in ("stabilny", "ruch"), f"{id_}: odcinek typ={o.get('typ')} nieznany")
                check(o.get("od_s") is not None and o.get("do_s") is not None and o["od_s"] <= o["do_s"], f"{id_}: odcinek {o} od_s>do_s")
            srodek = ruch.get("srodek")
            check(srodek is None or ("od_s" in srodek and "do_s" in srodek), f"{id_}: ruch.srodek={srodek} zly ksztalt")
            brzegi = ruch.get("brzegi") or {}
            check(isinstance(brzegi.get("poczatek_ruch"), bool) and isinstance(brzegi.get("koniec_ruch"), bool),
                  f"{id_}: ruch.brzegi={brzegi} pola nie sa bool")
            check(isinstance(ruch.get("pary_niepewne"), int) and ruch["pary_niepewne"] >= 0,
                  f"{id_}: ruch.pary_niepewne={ruch.get('pary_niepewne')}")
            mediana, p90 = ruch.get("mediana_jitter_pct"), ruch.get("p90_jitter_pct")
            if mediana is not None and p90 is not None:
                check(p90 >= mediana, f"{id_}: p90_jitter_pct {p90} < mediana_jitter_pct {mediana}")

    # --- kalibracja ruchu v0.2: werdykty Kuby 2026-09-05 (patrz CLAUDE.md sesji) ---
    # DSCF1414 - kamera na murku, niestabilny tylko poczatek (i pewnie koniec).
    # DSCF3066 - hero Anagi, ogolnie bardziej shaky niz 1414 (porownanie median).
    # DSCF2988 - statyw, klasa "static", jitter srodka < 0.05.
    ruch_cases = {}
    reports_ruch = {}
    for ruch_id in ("DSCF1414", "DSCF3066", "DSCF2988"):
        rp = report_dir / f"{ruch_id}.json"
        if not rp.exists():
            check(False, f"kalibracja ruchu: brak raportu {ruch_id} (odpal measure.py --force na tym klipie)")
            continue
        dane = json.loads(rp.read_text(encoding="utf-8"))
        reports_ruch[ruch_id] = dane
        ruch_cases[ruch_id] = dane.get("ruch", {})

    # --- tonalnosc.profil + skop "przebieg" (v0.3): te 3 raporty sa zawsze
    # swieze (regenerowane przez bramke measure.py --force wyzej), wiec
    # profil MUSI tu byc - w odroznieniu od CASES powyzej (DSCF3236/GX010042),
    # ktore moga byc starsze i profilu jeszcze nie miec (regeneracja to
    # osobna decyzja, jak przy ruch v0.2 - patrz komentarz nad CASES).
    for ruch_id, dane in reports_ruch.items():
        profil = (dane.get("tonalnosc") or {}).get("profil")
        check(isinstance(profil, list) and len(profil) > 0, f"{ruch_id}: tonalnosc.profil puste/brak")
        for p in profil or []:
            check(isinstance(p.get("t_s"), int), f"{ruch_id}: profil_jasnosci.t_s={p.get('t_s')} nie jest int")
            for k in ("p5", "p50", "p99"):
                v = p.get(k)
                check(isinstance(v, (int, float)) and 0.0 <= v <= 1.0, f"{ruch_id}: profil_jasnosci.{k}={v} poza 0..1 (t_s={p.get('t_s')})")
            if all(p.get(k) is not None for k in ("p5", "p50", "p99")):
                check(p["p5"] <= p["p50"] <= p["p99"], f"{ruch_id}: profil_jasnosci {p} nie rosnie monotonicznie")

        skopy_ruch = dane.get("skopy") or []
        przebiegi = [s for s in skopy_ruch if s.get("typ") == "przebieg"]
        check(len(przebiegi) == 1, f"{ruch_id}: oczekiwano dokladnie 1 wpisu skopy typu 'przebieg', jest {len(przebiegi)}")
        for s in przebiegi:
            check(s.get("t_s") is None, f"{ruch_id}: skop przebieg t_s={s.get('t_s')} oczekiwano null")
            pp = cache_root / s["plik"]
            check(pp.exists(), f"{ruch_id}: brak pliku przebiegu {pp}")
            if pp.exists():
                check(pp.stat().st_size <= MAX_PNG_BYTES, f"{ruch_id}: {pp} > 500 KB ({pp.stat().st_size} B)")

    if len(ruch_cases) == 3:
        r1414, r3066, r2988 = ruch_cases["DSCF1414"], ruch_cases["DSCF3066"], ruch_cases["DSCF2988"]

        klasa_1414 = r1414.get("klasa") or []
        check(
            "postawiona" in klasa_1414 or "static" in klasa_1414,
            f"DSCF1414: klasa={klasa_1414}, oczekiwano 'postawiona' albo 'static' (kamera na murku)",
        )
        srodek_1414 = r1414.get("srodek")
        n_sec_1414 = len(r1414.get("profil") or []) or 1
        check(srodek_1414 is not None, "DSCF1414: brak wykrytego stabilnego srodka")
        if srodek_1414 is not None:
            dl_1414 = srodek_1414["do_s"] - srodek_1414["od_s"] + 1
            check(
                dl_1414 >= 0.5 * n_sec_1414,
                f"DSCF1414: srodek {srodek_1414} to {dl_1414}/{n_sec_1414} s, oczekiwano wiekszosci klipu",
            )
        check(
            (r1414.get("brzegi") or {}).get("poczatek_ruch") is True,
            f"DSCF1414: brzegi.poczatek_ruch={(r1414.get('brzegi') or {}).get('poczatek_ruch')}, oczekiwano true",
        )

        med_3066 = r3066.get("mediana_jitter_srodka_pct")
        med_1414 = r1414.get("mediana_jitter_srodka_pct")
        check(
            med_3066 is not None and med_1414 is not None and med_3066 > med_1414,
            f"DSCF3066 vs DSCF1414: mediana_jitter_srodka_pct {med_3066} nie jest > {med_1414} (Kuba: 3066 bardziej shaky)",
        )

        klasa_2988 = r2988.get("klasa") or []
        check("static" in klasa_2988, f"DSCF2988: klasa={klasa_2988}, oczekiwano 'static' (statyw)")
        jitter_2988 = r2988.get("jitter_rms_pct")
        check(
            jitter_2988 is not None and jitter_2988 < 0.05,
            f"DSCF2988: jitter_rms_pct={jitter_2988}, oczekiwano < 0.05 (statyw)",
        )

    if failures:
        print(f"SMOKE TEST: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("SMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
