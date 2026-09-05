"""Wektory testowe klucza v1 (Dexter, raport "Shadow notes - nastepca" 2026-09-05, sekcja 8)
+ rozszerzenia sonny-eyes. Bez pytest: .venv/Scripts/python.exe tests/test_keys.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from eyes.keys import assign_ids, qualified, split_base_ext, strip_variant  # noqa: E402


def ids(paths):
    return {k: v.id for k, v in assign_ids(paths).items()}


# 1: pt.2
assert ids(["dzień 4/video/DSCF1646.MOV"]) == {"dzień 4/video/DSCF1646.MOV": "DSCF1646"}

# 2-4: Foto - RAF + JPG + _IG + xmp = jeden rekord, cztery warianty
r = assign_ids(["Dzień 9/DSCF0011.JPG", "Dzień 9/DSCF0011.RAF", "Obrobione/DSCF0011_IG.jpg", "Dzień 9/DSCF0011.xmp"])
assert {v.id for v in r.values()} == {"DSCF0011"}, r
assert {v.variant for v in r.values()} == {"jpg", "raf", "ig", "xmp"}, r
assert not any(v.collision for v in r.values())

# 5-6: pt.2 kolizja DSCF2148 (ddfg sortuje sie przed foto -> ddfg zachowuje czyste id)
r = ids(["dzień 4/foto/DSCF2148.MOV", "dzień 4/ddfg/DSCF2148.MOV"])
assert r["dzień 4/ddfg/DSCF2148.MOV"] == "DSCF2148", r
assert r["dzień 4/foto/DSCF2148.MOV"] == "DSCF2148@foto", r

# 7: Assets wav, sufiks -V1 zostaje w nazwie
p = "Muzyka/CT-EP01-Above-Clouds-LOFI-V1.wav"
assert ids([p])[p] == "CT-EP01-Above-Clouds-LOFI-V1"

# 8: sufiks spoza listy zostaje
assert ids(["Grafiki/logo_export.png"])["Grafiki/logo_export.png"] == "logo_export"

# 9: EP03 glebokie foldery
p = "dzień 6/Teneryfa/a/100_FUJI/DSCF2393.MOV"
assert ids([p])[p] == "DSCF2393"

# 10: adres poza projektem
assert qualified("Canarian Tweety Foto", "DSCF0011") == "Canarian Tweety Foto/DSCF0011"

# rownosc bez wielkosci liter (id zachowuje wielkosc z pliku), rozne rozszerzenia = jeden rekord
r = assign_ids(["a/dscf0011.jpg", "b/DSCF0011.RAF"])
assert {v.id.lower() for v in r.values()} == {"dscf0011"} and not any(v.collision for v in r.values())

# _IG bez wielkosci liter; inne koncowki zostaja; ostatnie rozszerzenie
assert strip_variant("DSCF0011_ig") == ("DSCF0011", "ig")
assert strip_variant("DSCF0011_final") == ("DSCF0011_final", None)
assert split_base_ext("Anime.Opener.v2.MOV") == ("Anime.Opener.v2", "mov")

# ponad spec: ten sam folder nadrzedny w dwu miejscach (Dzień 7: 100_FUJI i DCIM/100_FUJI) -> ~2 + ostrzezenie
r = assign_ids(["Dzień 7/100_FUJI/DSCF2988.MOV", "Dzień 7/DCIM/100_FUJI/DSCF2988.MOV", "X/100_FUJI/DSCF2988.MOV"])
got = sorted(v.id for v in r.values())
assert got == ["DSCF2988", "DSCF2988@100_FUJI", "DSCF2988@100_FUJI~2"], got
assert sum(1 for v in r.values() if v.warning) == 1

# znak # w folderze nie ma znaczenia, bo id bierze tylko nazwe pliku
p = "#39-42 Canarian Tweety Series/Dzień 7/100_FUJI/DSCF3236.MOV"
assert ids([p])[p] == "DSCF3236"

print("test_keys: PASS (10 wektorow Dextera + 6 rozszerzen)")
