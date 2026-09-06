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

Sprawdza: liste 8 narzedzi (dokladnie te nazwy), probe_clip na realnym
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
import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mcp import types  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

# Realny klip Fuji Kuby, ten sam folder co tests/test_runner.py:FOLDER_2_3_KLIPOW.
FUJI_FOLDER = Path(
    r"C:\Users\jdziu\JDHole Production\VIdeo\Vlog\#39-42 Canarian Tweety Series\Dzień 7\100_FUJI"
)

EXPECTED_TOOLS = {
    "probe_clip", "measure_clip", "get_report", "list_reports",
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

                # --- lista narzedzi: dokladnie te 8 nazwy ---
                tools_result = await session.list_tools()
                names = {t.name for t in tools_result.tools}
                check(names == EXPECTED_TOOLS, f"list_tools: {sorted(names)} != {sorted(EXPECTED_TOOLS)}")

                # --- probe_clip na realnym klipie Fuji ---
                if not FUJI_FOLDER.is_dir():
                    print(f"SKIP: folder z materialem autora nie istnieje, pomijam probe/measure/list/get/review: {FUJI_FOLDER}")
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

                        # --- probe_clip na nieistniejacej sciezce: czytelny blad, nie traceback ---
                        r_bad = await session.call_tool("probe_clip", {"path": str(tmp / "nie_ma_takiego_pliku.mov")})
                        check(r_bad.is_error, "probe_clip na nieistniejacej sciezce powinno zwrocic is_error=True")
                        check(
                            "not found" in tool_error_text(r_bad).lower() or "nie" in tool_error_text(r_bad).lower(),
                            f"probe_clip error text nieczytelny: {tool_error_text(r_bad)!r}",
                        )

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
