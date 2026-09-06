"""Test dymny CLI (bramka P1). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_cli.py

Sprawdza parsowanie sciezek w `python -m eyes measure/batch/profile`:
--files/--folder/--ids maja dzialac zarowno jako `--files a --files b`
(powtorzona flaga), jak i `--files a b` (kilka wartosci po jednej fladze)
i forma mieszana. Uzywa click.testing.CliRunner z podmienionymi funkcjami
cmd_measure.main/cmd_batch.main/cmd_profile.main (przechwytuja argv,
NIC nie licza) - zero realnego pomiaru w tym pliku.
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from click.testing import CliRunner  # noqa: E402

from eyes import cli as cli_mod  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


captured: dict = {}


def _fake_main(argv):
    captured["argv"] = list(argv)
    return 0


def _files_from_argv(argv: list[str]) -> list[str]:
    """Wyciaga wartosci nastepujace po '--files' az do kolejnej opcji '--xxx'."""
    return _values_after(argv, "--files")


def _values_after(argv: list[str], flag: str) -> list[str]:
    """Wszystkie wartosci wystepujace po KAZDYM wystapieniu `flag` w argv, az do
    kolejnej opcji '--xxx'. Obsluguje oba style budowania argv w eyes/cli.py:
    jedna flaga + wiele wartosci (measure --files, profile --ids) i flaga
    powtorzona per wartosc (batch --folder)."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == flag:
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                out.append(argv[i])
                i += 1
        else:
            i += 1
    return out


def test_measure_forms() -> None:
    runner = CliRunner()
    cli_mod.cmd_measure.main = _fake_main

    # forma 1: flaga powtorzona
    captured.clear()
    result = runner.invoke(cli_mod.cli, ["measure", "--project", "T", "--files", "a.mov", "--files", "b.mov"])
    check(result.exit_code == 0, f"measure --files a --files b: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(_files_from_argv(captured.get("argv", [])) == ["a.mov", "b.mov"], f"measure --files a --files b: argv niepoprawne: {captured.get('argv')}")

    # forma 2: kilka sciezek po jednej fladze
    captured.clear()
    result = runner.invoke(cli_mod.cli, ["measure", "--project", "T", "--files", "a.mov", "b.mov"])
    check(result.exit_code == 0, f"measure --files a b: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(_files_from_argv(captured.get("argv", [])) == ["a.mov", "b.mov"], f"measure --files a b: argv niepoprawne: {captured.get('argv')}")

    # forma mieszana: kilka sciezek po fladze + druga flaga
    captured.clear()
    result = runner.invoke(cli_mod.cli, ["measure", "--project", "T", "--files", "a.mov", "b.mov", "--files", "c.mov"])
    check(result.exit_code == 0, f"measure forma mieszana: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(
        sorted(_files_from_argv(captured.get("argv", []))) == ["a.mov", "b.mov", "c.mov"],
        f"measure forma mieszana: argv niepoprawne: {captured.get('argv')}",
    )

    # opcje PO sciezkach nadal sie parsuja
    captured.clear()
    result = runner.invoke(cli_mod.cli, ["measure", "--project", "T", "--files", "a.mov", "b.mov", "--force"])
    check(result.exit_code == 0, f"measure --files a b --force: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check("--force" in captured.get("argv", []), f"measure --files a b --force: brak --force w argv: {captured.get('argv')}")
    check(_files_from_argv(captured.get("argv", [])) == ["a.mov", "b.mov"], f"measure --files a b --force: argv sciezek niepoprawne: {captured.get('argv')}")


def test_batch_forms() -> None:
    runner = CliRunner()
    cli_mod.cmd_batch.main = _fake_main

    captured.clear()
    result = runner.invoke(cli_mod.cli, ["batch", "--project", "T", "--folder", "f1", "--folder", "f2"])
    check(result.exit_code == 0, f"batch --folder f1 --folder f2: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(_values_after(captured.get("argv", []), "--folder") == ["f1", "f2"], f"batch --folder f1 --folder f2: argv niepoprawne: {captured.get('argv')}")
    check(captured.get("argv", []).count("--folder") == 1, f"batch: flaga --folder musi wystapic RAZ (argparse nargs='+' nadpisuje powtorzona): {captured.get('argv')}")

    captured.clear()
    result = runner.invoke(cli_mod.cli, ["batch", "--project", "T", "--folder", "f1", "f2"])
    check(result.exit_code == 0, f"batch --folder f1 f2: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(_values_after(captured.get("argv", []), "--folder") == ["f1", "f2"], f"batch --folder f1 f2: argv niepoprawne: {captured.get('argv')}")

    # opcje PO sciezkach (--force --detach) nadal sie parsuja; --detach jest
    # obslugiwane w eyes/cli.py PRZED wywolaniem cmd_batch.main (proces
    # odczepiony), wiec tu sprawdzamy przez brak bledu parsera + kod inny niz
    # "Got unexpected extra argument".
    captured.clear()
    result = runner.invoke(cli_mod.cli, ["batch", "--project", "T", "--folder", "f1", "f2", "--force", "--limit", "1"])
    check(result.exit_code == 0, f"batch --folder f1 f2 --force --limit 1: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check("--force" in captured.get("argv", []), f"batch --folder f1 f2 --force: brak --force w argv: {captured.get('argv')}")
    check(_values_after(captured.get("argv", []), "--folder") == ["f1", "f2"], f"batch --folder f1 f2 --force: argv folderow niepoprawne: {captured.get('argv')}")


def test_profile_ids() -> None:
    runner = CliRunner()
    cli_mod.cmd_profile.main = _fake_main

    captured.clear()
    result = runner.invoke(cli_mod.cli, ["profile", "--project", "T", "--ids", "ID1", "--ids", "ID2"])
    check(result.exit_code == 0, f"profile --ids ID1 --ids ID2: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(_values_after(captured.get("argv", []), "--ids") == ["ID1", "ID2"], f"profile --ids ID1 --ids ID2: argv niepoprawne: {captured.get('argv')}")

    captured.clear()
    result = runner.invoke(cli_mod.cli, ["profile", "--project", "T", "--ids", "ID1", "ID2"])
    check(result.exit_code == 0, f"profile --ids ID1 ID2: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check(_values_after(captured.get("argv", []), "--ids") == ["ID1", "ID2"], f"profile --ids ID1 ID2: argv niepoprawne: {captured.get('argv')}")

    # brak --ids w ogole -> profile mierzy wszystkie raporty projektu (argv bez --ids)
    captured.clear()
    result = runner.invoke(cli_mod.cli, ["profile", "--project", "T"])
    check(result.exit_code == 0, f"profile bez --ids: exit_code={result.exit_code}, output={result.output!r}, exc={result.exception!r}")
    check("--ids" not in captured.get("argv", []), f"profile bez --ids: --ids nie powinno byc w argv: {captured.get('argv')}")


def main() -> int:
    test_measure_forms()
    test_batch_forms()
    test_profile_ids()

    if failures:
        print(f"TEST_CLI: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_CLI: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
