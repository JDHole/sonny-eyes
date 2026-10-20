"""Test dymny modulu assetow (bramka). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_asset.py

Mierzy 1 WAV (AUDIO_WAV z tests/_material.py, brak = SKIP) do
TYMCZASOWEGO --out (NIE do prawdziwego cache/reports): komplet kluczy
najwyzszego poziomu (w tym audio), audio.lufs_i liczba < 0, pliki fali/kafla
> 0 B. Osobno (bez pomiaru, sama logika): dyspozytor rozszerzen
eyes.cmd_asset._kind_for_ext i pomijanie wariantow _IG/_stock/_export
obrazow w eyes.cmd_batch.zbierz_assets (audio i wideo z taka koncowka sa
mierzone), na pustych plikach.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_asset  # noqa: E402
from eyes import cmd_batch  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402

from _material import material, skip_reason  # noqa: E402

WAV = material("AUDIO_WAV")

TOP_KEYS = [
    "wersja_metryk", "id", "projekt", "zrodlo", "stream", "okno_pomiaru",
    "tonalnosc", "kolor", "ostrosc", "szum", "ruch", "plynnosc", "montaz",
    "klatki", "skopy", "flagi_prowizoryczne", "progi_prowizoryczne",
    "werdykty", "niepewnosc", "pomiar", "audio",
]

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def test_dyspozytor() -> None:
    check(cmd_asset._kind_for_ext("wav") == "audio", "kind('wav') != audio")
    check(cmd_asset._kind_for_ext("mp3") == "audio", "kind('mp3') != audio")
    check(cmd_asset._kind_for_ext("m4a") == "audio", "kind('m4a') != audio")
    check(cmd_asset._kind_for_ext("flac") == "audio", "kind('flac') != audio")
    check(cmd_asset._kind_for_ext("aac") == "audio", "kind('aac') != audio")
    check(cmd_asset._kind_for_ext("png") == "image", "kind('png') != image")
    check(cmd_asset._kind_for_ext("jpg") == "image", "kind('jpg') != image")
    check(cmd_asset._kind_for_ext("webp") == "image", "kind('webp') != image")
    check(cmd_asset._kind_for_ext("svg") == "svg", "kind('svg') != svg")
    check(cmd_asset._kind_for_ext("mp4") == "video", "kind('mp4') != video")
    check(cmd_asset._kind_for_ext("mov") == "video", "kind('mov') != video")
    check(cmd_asset._kind_for_ext("xyz") is None, "kind('xyz') powinno byc None")


def test_zbierz_assets_pomija_warianty(tmp_root: Path) -> None:
    folder = tmp_root / "assets_logic"
    folder.mkdir(parents=True, exist_ok=True)
    nazwy = [
        "a.wav", "b.png", "b_IG.png", "c_stock.jpg", "d.svg", "d_export.svg", "e.mp4", "notatka.txt",
        # audio i wideo z koncowka to samodzielne pliki, nie kopie obrazu (Kuba 20.10)
        "track_stock.wav", "muzyka_export.mp3", "clip_export.mp4", "ujecie_stock.MOV",
    ]
    for n in nazwy:
        (folder / n).write_bytes(b"")
    wynik = sorted(p.name for p in cmd_batch.zbierz_assets([str(folder)]))
    oczekiwane = sorted([
        "a.wav", "b.png", "d.svg", "e.mp4",
        "track_stock.wav", "muzyka_export.mp3", "clip_export.mp4", "ujecie_stock.MOV",
    ])
    check(wynik == oczekiwane, f"zbierz_assets: {wynik} != {oczekiwane}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="eyes_test_asset_") as tmp_s:
        tmp = Path(tmp_s)
        cfg = load_config(None, overrides=overrides_from_out(str(tmp / "out")))

        test_dyspozytor()
        test_zbierz_assets_pomija_warianty(tmp)

        powod = skip_reason("AUDIO_WAV", WAV)
        if powod:
            print(powod)
        else:
            hash_by_path = {WAV.resolve(): "test-hash"}
            r = cmd_asset.measure_audio(
                WAV.resolve(), project="TestAsset", cfg=cfg, force=True,
                hash_by_path=hash_by_path, file_paths=[WAV.resolve()],
            )
            check(r["status"] == "ok", f"WAV: status={r['status']} (oczekiwano ok)")
            if r["status"] == "ok":
                report_path = Path(r["raport"])
                check(report_path.exists(), f"WAV: brak pliku raportu {report_path}")
                data = json.loads(report_path.read_text(encoding="utf-8"))

                for key in TOP_KEYS:
                    check(key in data, f"WAV: brak klucza najwyzszego poziomu '{key}'")

                audio = data.get("audio", {})
                lufs = audio.get("lufs_i")
                check(isinstance(lufs, (int, float)) and lufs < 0, f"WAV: audio.lufs_i={lufs!r} oczekiwano liczby < 0")
                check(audio.get("sample_rate") == 48000, f"WAV: audio.sample_rate={audio.get('sample_rate')} oczekiwano 48000")
                check(audio.get("channels") == 2, f"WAV: audio.channels={audio.get('channels')} oczekiwano 2")
                check(isinstance(audio.get("cisza_start_s"), (int, float)), "WAV: audio.cisza_start_s nie jest liczba")
                check(isinstance(audio.get("cisza_koniec_s"), (int, float)), "WAV: audio.cisza_koniec_s nie jest liczba")

                check(data.get("tonalnosc") is None, f"WAV: tonalnosc={data.get('tonalnosc')} oczekiwano null dla audio")
                check(data.get("kolor") is None, f"WAV: kolor={data.get('kolor')} oczekiwano null dla audio")
                check(data.get("ostrosc") is None, f"WAV: ostrosc={data.get('ostrosc')} oczekiwano null dla audio")
                check(data.get("szum") is None, f"WAV: szum={data.get('szum')} oczekiwano null dla audio")
                check(data.get("ruch") == {"klasa": [], "metoda": None}, f"WAV: ruch={data.get('ruch')}")
                check(data.get("skopy") == [], f"WAV: skopy={data.get('skopy')} oczekiwano [] dla audio")
                check(data.get("zrodlo", {}).get("rodzaj") == "audio", f"WAV: zrodlo.rodzaj={data.get('zrodlo', {}).get('rodzaj')}")

                cache_root = Path(cfg.cache_root)
                klatki = data.get("klatki", [])
                check(len(klatki) == 3, f"WAV: oczekiwano 3 klatki (pierwsza/najostrzejsza/kafel), jest {len(klatki)}")
                for fr in klatki:
                    p = cache_root / fr["plik"]
                    check(p.exists(), f"WAV: brak pliku {p}")
                    if p.exists():
                        check(p.stat().st_size > 0, f"WAV: {p} ma 0 B")

    if failures:
        print(f"TEST_ASSET: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_ASSET: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
