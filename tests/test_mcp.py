"""Test dymny MCP servera (bramka, bez pytest):

    .venv/Scripts/python.exe tests/test_mcp.py

Odpala `python -m eyes mcp` jako podproces (klient stdio z pakietu mcp:
mcp.client.stdio + ClientSession), tak jak zrobilby to Claude Code/Claude
Desktop/Cursor. Izolacja od danych Kuby: EYES_OUT wskazuje na katalog
tymczasowy, EYES_CONFIG na NIEISTNIEJACY plik - patrz eyes/config.py:
config.toml obok repo (prawdziwy, z sciezkami produkcyjnymi Kuby) jest
czytany tylko gdy istnieje pod finalna sciezka; samo EYES_OUT NIE
wystarczy do izolacji, bo prawdziwy config.toml ustawia cache_root i
reports_root JAWNIE (wygrywaja z out_root pochodzacym z EYES_OUT) -
przekierowanie EYES_CONFIG na plik, ktory nie istnieje, daje pusty
config (data={}) i wtedy EYES_OUT faktycznie rzadzi wszystkim.

Bez materialu (zawsze): lista 10 narzedzi, czytelny blad na nieistniejacej
sciezce, measure_photo na syntetycznym JPG i measure_asset na syntetycznym
WAV (generowane w tescie - potrzebny tylko ffmpeg), batch_start z
kind="foto" na dwoch folderach z syntetycznymi JPG (detach, czekanie na
koniec, 2 zmierzone), batch_start z nieznanym kind i pusta lista folderow
(czytelny blad). Z materialem FUJI_FOLDER dodatkowo:
probe_clip na realnym
klipie Fuji, measure_clip (raport ladujacy sie do katalogu tymczasowego,
NIE do cache/reports Kuby), cache przy drugim wywolaniu bez --force,
list_reports, get_report(compact=True) bez ruch.profil/tonalnosc.profil,
review_page, batch_status na projekcie bez zadnego runnera (czytelnie
"brak", nie wyjatek), i czytelny blad (ToolError, nie traceback) na
nieistniejacej sciezce.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import json
import math
import os
import struct
import tempfile
import time
import wave
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mcp import types  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

# Realny folder klipow Fuji (material FUJI_FOLDER), ten sam co w tests/test_runner.py.
from _material import material, skip_reason  # noqa: E402

FUJI_FOLDER = material("FUJI_FOLDER")

EXPECTED_TOOLS = {
    "probe_clip", "measure_clip", "measure_photo", "measure_asset", "get_report", "list_reports",
    "batch_start", "batch_status", "batch_stop", "review_page",
}

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def tool_result_data(result: types.CallToolResult):
    """structured_content jesli jest, inaczej sparsowany JSON z pierwszego
    bloku tekstowego. Narzedzie zwracajace `list[...]` (list_reports) ma
    structured_content opakowane w {"result": [...]} - JSON Schema wymaga
    obiektu na najwyzszym poziomie, wiec SDK owija kazdy nie-obiektowy typ
    zwracany w ten sposob; odpakowujemy to tutaj, zeby wołajacy zawsze dostal
    to, co faktycznie zwrocilo narzedzie (dict lub list), nie kopercie SDK."""
    data = result.structured_content
    if data is None:
        for block in result.content:
            if isinstance(block, types.TextContent):
                data = json.loads(block.text)
                break
    if isinstance(data, dict) and list(data.keys()) == ["result"]:
        return data["result"]
    return data


def tool_error_text(result: types.CallToolResult) -> str:
    parts = [b.text for b in result.content if isinstance(b, types.TextContent)]
    return " ".join(parts)


def syntetyczny_jpg(path: Path, kolor: tuple[int, int, int]) -> None:
    """JPG z gradientem (zeby percentyle tonalnosci nie byly wszystkie rowne)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.linear_gradient("L").resize((320, 200)).convert("RGB")
    im = Image.blend(im, Image.new("RGB", im.size, kolor), 0.3)
    im.save(path, "JPEG", quality=90)


def syntetyczny_wav(path: Path, sekundy: float = 2.0, hz: float = 440.0) -> None:
    """Mono 16-bit 48 kHz: 0.5 s ciszy, sinus, 0.5 s ciszy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = 48000
    probki = []
    for n in range(int(sr * sekundy)):
        t = n / sr
        a = 0.0 if t < 0.5 or t > sekundy - 0.5 else 0.5 * math.sin(2 * math.pi * hz * t)
        probki.append(int(a * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(probki)}h", *probki))


async def bez_materialu(session: ClientSession, tmp: Path, out_dir: Path) -> None:
    """Czesc MCP, ktora nie potrzebuje zadnego materialu autora."""
    # --- nieistniejaca sciezka: czytelny blad (ToolError), nie traceback ---
    for narzedzie in ("probe_clip", "measure_photo", "measure_asset"):
        r_bad = await session.call_tool(narzedzie, {"path": str(tmp / "nie_ma_takiego_pliku.mov")})
        check(r_bad.is_error, f"{narzedzie} na nieistniejacej sciezce powinno zwrocic is_error=True")
        check("not found" in tool_error_text(r_bad).lower(), f"{narzedzie} error text nieczytelny: {tool_error_text(r_bad)!r}")

    # --- measure_photo na syntetycznym JPG ---
    jpg = tmp / "material" / "foto" / "SYN0001.jpg"
    syntetyczny_jpg(jpg, (180, 120, 60))
    r = await session.call_tool("measure_photo", {"path": str(jpg), "project": "TestMcpFoto", "force": True})
    check(not r.is_error, f"measure_photo error: {tool_error_text(r)}")
    rep_f = tool_result_data(r) or {}
    check(rep_f.get("id") == "SYN0001", f"measure_photo: id={rep_f.get('id')} oczekiwano SYN0001")
    check(rep_f.get("cached") is False, f"measure_photo: cached={rep_f.get('cached')} oczekiwano False")
    for key in ("exif", "kadr", "warianty", "tonalnosc"):
        check(key in rep_f, f"measure_photo: brak klucza '{key}'")
    check((rep_f.get("kadr") or {}).get("w") == 320, f"measure_photo: kadr.w={(rep_f.get('kadr') or {}).get('w')} oczekiwano 320")
    check(str(out_dir) in str(rep_f.get("report_path", "")), f"measure_photo: report_path {rep_f.get('report_path')} poza EYES_OUT")
    r = await session.call_tool("measure_photo", {"path": str(jpg), "project": "TestMcpFoto"})
    check((tool_result_data(r) or {}).get("cached") is True, "measure_photo drugi raz bez force: cached nie jest True")

    # --- measure_asset na syntetycznym WAV ---
    wav = tmp / "material" / "audio" / "syn_ton.wav"
    syntetyczny_wav(wav)
    r = await session.call_tool("measure_asset", {"path": str(wav), "project": "TestMcpAsset", "force": True})
    check(not r.is_error, f"measure_asset error: {tool_error_text(r)}")
    rep_a = tool_result_data(r) or {}
    audio = rep_a.get("audio") or {}
    check(rep_a.get("id") == "syn_ton", f"measure_asset: id={rep_a.get('id')} oczekiwano syn_ton")
    check((rep_a.get("zrodlo") or {}).get("rodzaj") == "audio", f"measure_asset: zrodlo.rodzaj={(rep_a.get('zrodlo') or {}).get('rodzaj')}")
    check(audio.get("lufs_i") is not None, f"measure_asset: audio.lufs_i={audio.get('lufs_i')}")
    czas = audio.get("czas_s")
    check(isinstance(czas, (int, float)) and abs(czas - 2.0) < 0.1, f"measure_asset: audio.czas_s={czas} oczekiwano ~2.0")
    fala = [k for k in rep_a.get("klatki") or [] if k.get("rola") == "najostrzejsza"]
    check(len(fala) == 1 and fala[0]["plik"].endswith("_fala.png"), f"measure_asset: klatka najostrzejsza={fala}")

    # --- plik bez dekodera nie oddaje cudzego raportu o tym samym id ---
    # ikona.png zapisuje ikona.json; ikona.svg (brak dekodera, CLI konczy sie
    # kodem 0 bez zapisu) z force=True ma dac blad, nie raport PNG jako swiezy
    png = tmp / "material" / "ikony" / "ikona.png"
    syntetyczny_jpg(png.with_suffix(".jpg"), (10, 200, 10))
    Image.open(png.with_suffix(".jpg")).save(png, "PNG")
    png.with_suffix(".jpg").unlink()
    r = await session.call_tool("measure_asset", {"path": str(png), "project": "TestMcpIkona", "force": True})
    check(not r.is_error, f"measure_asset png error: {tool_error_text(r)}")
    svg = png.with_suffix(".svg")
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>', encoding="utf-8")
    r = await session.call_tool("measure_asset", {"path": str(svg), "project": "TestMcpIkona", "force": True})
    check(r.is_error and "decoder" in tool_error_text(r), f"measure_asset svg po png: oczekiwano bledu brak dekodera, jest {tool_error_text(r)[:200]!r}")

    # --- batch_start: zle wejscia = czytelny blad ---
    r = await session.call_tool("batch_start", {"project": "TestMcpBatch", "folders": [str(tmp)], "kind": "obrazki"})
    check(r.is_error and "kind" in tool_error_text(r), f"batch_start z nieznanym kind: {tool_error_text(r)!r}")
    r = await session.call_tool("batch_start", {"project": "TestMcpBatch", "folders": []})
    check(r.is_error, "batch_start z pusta lista folderow powinno zwrocic is_error=True")

    # --- batch_start kind=foto: dwa foldery, po jednym JPG w kazdym ---
    f1, f2 = tmp / "material" / "batch_a", tmp / "material" / "batch_b"
    syntetyczny_jpg(f1 / "SYN1001.jpg", (40, 90, 160))
    syntetyczny_jpg(f2 / "SYN1002.jpg", (160, 90, 40))
    project = "TestMcpBatch"
    r = await session.call_tool("batch_start", {"project": project, "folders": [str(f1), str(f2)], "kind": "foto"})
    check(not r.is_error, f"batch_start foto error: {tool_error_text(r)}")
    if r.is_error:
        return
    postep = {}
    deadline = time.time() + 180
    while time.time() < deadline:
        st = tool_result_data(await session.call_tool("batch_status", {"project": project})) or {}
        postep = st.get("postep") or {}
        if postep.get("status") in ("zakonczony", "zakonczony z bledami", "przerwany"):
            break
        if not st.get("alive") and postep.get("status") != "w toku":
            break
        await asyncio.sleep(1)
    check(postep.get("status") == "zakonczony", f"batch_start foto: status={postep.get('status')!r} oczekiwano zakonczony")
    # 2, nie 1: oba foldery doszly do przemialu (powtorzona flaga --folder zjadala wszystkie poza ostatnim)
    check(postep.get("plikow") == 2 and postep.get("ok") == 2, f"batch_start foto: plikow={postep.get('plikow')} ok={postep.get('ok')} oczekiwano 2/2")
    rows = tool_result_data(await session.call_tool("list_reports", {"project": project})) or []
    check(sorted(x.get("id") for x in rows) == ["SYN1001", "SYN1002"], f"batch_start foto: raporty {rows}")


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="eyes_test_mcp_") as tmp_s:
        tmp = Path(tmp_s)
        out_dir = tmp / "out"
        fake_config = tmp / "no_such_config.toml"  # celowo nie istnieje

        env = dict(os.environ)
        env["EYES_OUT"] = str(out_dir)
        env["EYES_CONFIG"] = str(fake_config)

        params = StdioServerParameters(
            command=sys.executable, args=["-m", "eyes", "mcp"], cwd=str(REPO_ROOT), env=env,
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # --- lista narzedzi: dokladnie te 10 nazw ---
                tools_result = await session.list_tools()
                names = {t.name for t in tools_result.tools}
                check(names == EXPECTED_TOOLS, f"list_tools: {sorted(names)} != {sorted(EXPECTED_TOOLS)}")

                await bez_materialu(session, tmp, out_dir)

                # --- probe_clip na realnym klipie Fuji ---
                powod = skip_reason("FUJI_FOLDER", FUJI_FOLDER)
                if powod or not FUJI_FOLDER.is_dir():
                    print(f"{powod or 'SKIP: FUJI_FOLDER to nie folder'}, pomijam probe/measure/list/get/review")
                else:
                    clips = sorted(FUJI_FOLDER.glob("DSCF*.MOV"))
                    if not clips:
                        print(f"SKIP: brak DSCF*.MOV w {FUJI_FOLDER}, pomijam czesc pomiarowa")
                        clips = []
                    else:
                        clip = clips[0]
                        clip_id = clip.stem

                        r = await session.call_tool("probe_clip", {"path": str(clip)})
                        check(not r.is_error, f"probe_clip error: {tool_error_text(r)}")
                        info = tool_result_data(r) or {}
                        check(info.get("codec") is not None, f"probe_clip: brak codec ({info})")
                        check(info.get("w") == 3840 or info.get("w") is not None, f"probe_clip: w={info.get('w')}")
                        check(info.get("kamera") == "Fuji", f"probe_clip: kamera={info.get('kamera')} oczekiwano Fuji")

                        # --- measure_clip: pelny pomiar do katalogu tymczasowego ---
                        project = "TestMcp"
                        r2 = await session.call_tool(
                            "measure_clip", {"path": str(clip), "project": project, "force": True},
                        )
                        check(not r2.is_error, f"measure_clip error: {tool_error_text(r2)}")
                        report = tool_result_data(r2) or {}
                        for key in ("wersja_metryk", "id", "zrodlo", "tonalnosc", "ruch", "werdykty", "niepewnosc"):
                            check(key in report, f"measure_clip: brak klucza '{key}' w raporcie")
                        check(report.get("werdykty") is None, f"measure_clip: werdykty={report.get('werdykty')} oczekiwano null")
                        check(report.get("cached") is False, f"measure_clip: cached={report.get('cached')} oczekiwano False (force=True)")
                        report_path = Path(report.get("report_path", ""))
                        check(report_path.exists(), f"measure_clip: report_path {report_path} nie istnieje na dysku")
                        check(
                            str(out_dir) in str(report_path),
                            f"measure_clip: report_path {report_path} NIE jest pod EYES_OUT {out_dir} (test pisalby do danych Kuby!)",
                        )

                        # --- drugi wywolanie bez force: cached=True, bez ponownego pomiaru ---
                        r2b = await session.call_tool("measure_clip", {"path": str(clip), "project": project})
                        check(not r2b.is_error, f"measure_clip (cache) error: {tool_error_text(r2b)}")
                        report_cached = tool_result_data(r2b) or {}
                        check(report_cached.get("cached") is True, f"measure_clip drugi raz: cached={report_cached.get('cached')} oczekiwano True")

                        # --- list_reports ---
                        r3 = await session.call_tool("list_reports", {"project": project})
                        check(not r3.is_error, f"list_reports error: {tool_error_text(r3)}")
                        rows = tool_result_data(r3) or []
                        check(isinstance(rows, list) and len(rows) == 1, f"list_reports: {rows}")
                        if rows:
                            check(rows[0].get("id") == clip_id, f"list_reports: id={rows[0].get('id')} oczekiwano {clip_id}")
                            check(rows[0].get("kamera") == "Fuji", f"list_reports: kamera={rows[0].get('kamera')}")
                            check("profil" not in json.dumps(rows[0]), "list_reports: nie powinno zawierac profili")

                        # --- get_report(compact=True): bez ruch.profil / tonalnosc.profil ---
                        r4 = await session.call_tool("get_report", {"project": project, "id": clip_id, "compact": True})
                        check(not r4.is_error, f"get_report error: {tool_error_text(r4)}")
                        compact_report = tool_result_data(r4) or {}
                        check("profil" not in (compact_report.get("ruch") or {}), "get_report compact: ruch.profil nadal obecny")
                        check("profil" not in (compact_report.get("tonalnosc") or {}), "get_report compact: tonalnosc.profil nadal obecny")
                        check((compact_report.get("ruch") or {}).get("klasa") is not None, "get_report compact: ruch.klasa zniknal (powinien zostac, to agregat)")

                        # --- get_report na nieistniejacym id: czytelny blad ---
                        r4b = await session.call_tool("get_report", {"project": project, "id": "NIE_MA_TAKIEGO"})
                        check(r4b.is_error, "get_report na nieistniejacym id powinno zwrocic is_error=True")

                        # --- review_page ---
                        r5 = await session.call_tool("review_page", {"project": project})
                        check(not r5.is_error, f"review_page error: {tool_error_text(r5)}")
                        review = tool_result_data(r5) or {}
                        review_path = Path(review.get("path", ""))
                        check(review_path.exists(), f"review_page: {review_path} nie istnieje")
                        check(review.get("reports") == 1, f"review_page: reports={review.get('reports')} oczekiwano 1")

                # --- batch_status na projekcie bez zadnego runnera: czytelnie "brak", nie wyjatek ---
                r6 = await session.call_tool("batch_status", {"project": "ProjektBezRunnera"})
                check(not r6.is_error, f"batch_status error: {tool_error_text(r6)}")
                status = tool_result_data(r6) or {}
                check(status.get("runner") is None, f"batch_status: runner={status.get('runner')} oczekiwano null")
                check(status.get("alive") is False, f"batch_status: alive={status.get('alive')} oczekiwano False")
                check(status.get("postep") is None, f"batch_status: postep={status.get('postep')} oczekiwano null")


def main() -> int:
    asyncio.run(run())

    if failures:
        print(f"TEST_MCP: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_MCP: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
