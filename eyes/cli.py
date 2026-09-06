"""Jedno wejscie CLI: `python -m eyes <podkomenda>`.

Kazda podkomenda jest cienkim tlumaczem opcji click -> argv, ktory woła
te sama funkcje `main(argv)` co odpowiadajacy jej alias w scripts/ (np.
scripts/measure.py). Cala logika mieszka w eyes/cmd_*.py i eyes/runner.py -
ten plik tylko sklada linie komend.

Wspolne opcje tam, gdzie ma to sens: --out (jeden folder wyjsciowy,
nadpisuje out_root/cache_root/reports_root), --config (jawna sciezka do
config.toml), --lut (tylko measure/batch: wymus LUT niezaleznie od
kamery), --no-gpu (tylko measure/batch: wymus dekodowanie CPU).
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import cmd_batch, cmd_dupes, cmd_measure, cmd_profile, cmd_review, runner  # noqa: E402
from eyes.config import load_config, overrides_from_out  # noqa: E402


def _out_config_lut_argv(out: str | None, config: str | None, lut: str | None, no_gpu: bool) -> list[str]:
    argv: list[str] = []
    if out:
        argv += ["--out", out]
    if config:
        argv += ["--config", config]
    if lut:
        argv += ["--lut", lut]
    if no_gpu:
        argv += ["--no-gpu"]
    return argv


@click.group()
@click.version_option(package_name="sonny-eyes", prog_name="eyes")
def cli() -> None:
    """sonny-eyes: perceptual measurement report for video clips (AI eyes for video)."""


@cli.command()
@click.option("--project", required=True, help="Project name (groups reports/cache).")
@click.option("--files", "files_", required=True, multiple=True, help="One or more clip paths to measure.")
@click.option("--out", default=None, help="Output root override (out_root/cache_root/reports_root).")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
@click.option("--lut", default=None, help="Force this LUT on every clip, regardless of camera.")
@click.option("--no-gpu", is_flag=True, default=False, help="Force CPU decoding (skip GPU/CUDA attempt).")
@click.option("--force", is_flag=True, default=False, help="Re-measure even if a report already exists.")
@click.option("--window-start", type=float, default=5.0, show_default=True, help="Measurement window start (seconds).")
@click.option("--window-len", type=float, default=20.0, show_default=True, help="Measurement window length (seconds).")
def measure(project, files_, out, config_path, lut, no_gpu, force, window_start, window_len) -> None:
    """Measure one or more clips and write a perception report per clip."""
    argv = ["--project", project, "--files", *files_]
    argv += _out_config_lut_argv(out, config_path, lut, no_gpu)
    if force:
        argv.append("--force")
    argv += ["--window-start", str(window_start), "--window-len", str(window_len)]
    sys.exit(cmd_measure.main(argv))


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--folder", required=True, multiple=True, help="One or more folders to scan recursively for camera files.")
@click.option("--porcja", default=None, help="Batch label recorded in _postep.json (default: first folder's name).")
@click.option("--force", is_flag=True, default=False, help="Re-measure even if a report already exists.")
@click.option("--no-gpu", is_flag=True, default=False, help="Force CPU decoding.")
@click.option("--limit", type=int, default=None, help="Only measure the first N files (test a batch).")
@click.option("--out", default=None, help="Output root override.")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
@click.option("--lut", default=None, help="Force this LUT on every clip, regardless of camera.")
@click.option("--detach", is_flag=True, default=False, help="Run as a detached background process; prints {pid,...} JSON and returns immediately.")
def batch(project, folder, porcja, force, no_gpu, limit, out, config_path, lut, detach) -> None:
    """Scan folder(s) recursively and measure every camera clip found."""
    argv = ["--project", project]
    for f in folder:
        argv += ["--folder", f]
    if porcja:
        argv += ["--porcja", porcja]
    if force:
        argv.append("--force")
    if limit is not None:
        argv += ["--limit", str(limit)]
    argv += _out_config_lut_argv(out, config_path, lut, no_gpu)

    if not detach:
        sys.exit(cmd_batch.main(argv))

    cfg = load_config(config_path, overrides=overrides_from_out(out))
    cmd = [sys.executable, "-m", "eyes", "batch", *argv]
    info = runner.start_detached(cmd, project=project, cache_root=Path(cfg.cache_root), porcja=porcja or Path(folder[0]).name)
    if info is None:
        click.echo(f'batch --detach: proces dla projektu "{project}" juz dziala (patrz `eyes status`)', err=True)
        sys.exit(3)
    click.echo(__import__("json").dumps(info, ensure_ascii=False))


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--out-file", default=None, help="Extra copy of the HTML page written to this path (for publishing).")
@click.option("--out", default=None, help="Output root override.")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
@click.option("--compact", is_flag=True, default=False, help="Small JPEGs (fits artifact size limits) instead of full PNGs.")
@click.option("--status", "status_text", default=None, help="Status banner text at the top of the page.")
def review(project, out_file, out, config_path, compact, status_text) -> None:
    """Build the HTML review page (bricks, numbers, flags) for a project."""
    argv = ["--project", project]
    if out_file:
        argv += ["--out-file", out_file]
    if out:
        argv += ["--out", out]
    if config_path:
        argv += ["--config", config_path]
    if compact:
        argv.append("--compact")
    if status_text:
        argv += ["--status", status_text]
    sys.exit(cmd_review.main(argv))


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--ids", multiple=True, default=None, help="Only these report ids (default: every report in the project).")
@click.option("--out", default=None, help="Output root override.")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
def profile(project, ids, out, config_path) -> None:
    """Redraw the 'clip profile' PNG from an existing report, without re-measuring."""
    argv = ["--project", project]
    if ids:
        argv += ["--ids", *ids]
    if out:
        argv += ["--out", out]
    if config_path:
        argv += ["--config", config_path]
    sys.exit(cmd_profile.main(argv))


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--verify", is_flag=True, default=False, help="Confirm candidates with a full sha1 hash (slow, reads whole files).")
@click.option("--out", default=None, help="Output root override.")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
def dupes(project, verify, out, config_path) -> None:
    """List duplicate-content candidates found during batch runs. Never deletes anything."""
    argv = ["--project", project]
    if verify:
        argv.append("--verify")
    if out:
        argv += ["--out", out]
    if config_path:
        argv += ["--config", config_path]
    sys.exit(cmd_dupes.main(argv))


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--out", default=None, help="Output root override.")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print machine-readable JSON instead of a text summary.")
def status(project, out, config_path, as_json) -> None:
    """Show whether a detached batch is running, plus its progress."""
    cfg = load_config(config_path, overrides=overrides_from_out(out))
    st = runner.get_status(project, Path(cfg.cache_root))
    if as_json:
        import json
        click.echo(json.dumps(st, ensure_ascii=False))
    else:
        click.echo(runner.format_status_text(st))


@cli.command()
@click.option("--project", required=True, help="Project name.")
@click.option("--out", default=None, help="Output root override.")
@click.option("--config", "config_path", default=None, help="Explicit path to config.toml.")
def stop(project, out, config_path) -> None:
    """Stop a detached batch (whole process tree, ffmpeg included)."""
    cfg = load_config(config_path, overrides=overrides_from_out(out))
    code, msg = runner.stop(project, Path(cfg.cache_root))
    click.echo(msg)
    sys.exit(code)


@cli.command()
def mcp() -> None:
    """Run the MCP server over stdio (tools: probe_clip, measure_clip, get_report,
    list_reports, batch_start, batch_status, batch_stop, review_page)."""
    from eyes.mcp_server import server

    server.run(transport="stdio")


@cli.command(name="_sleep", hidden=True)
@click.option("--project", required=True)
@click.option("--seconds", type=float, default=30.0)
@click.option("--out", default=None)
@click.option("--config", "config_path", default=None)
@click.option("--detach", is_flag=True, default=False)
def _sleep(project, seconds, out, config_path, detach) -> None:
    """Testowa podkomenda (Z3, tests/test_runner.py): spawnuje dziecko
    ktore spi dlugo, potem sama spi `--seconds` - zeby test mogl sprawdzic
    ubijanie calego drzewa procesow przez `eyes stop`. Nie ma zadnego
    zwiazku z pomiarem wideo."""
    argv = ["--project", project, "--seconds", str(seconds)]
    if out:
        argv += ["--out", out]
    if config_path:
        argv += ["--config", config_path]

    if not detach:
        sys.exit(_sleep_main(argv))

    cfg = load_config(config_path, overrides=overrides_from_out(out))
    cmd = [sys.executable, "-m", "eyes", "_sleep", *argv]
    info = runner.start_detached(cmd, project=project, cache_root=Path(cfg.cache_root), porcja="_sleep")
    if info is None:
        click.echo(f'_sleep --detach: proces dla projektu "{project}" juz dziala', err=True)
        sys.exit(3)
    click.echo(__import__("json").dumps(info, ensure_ascii=False))


def _sleep_main(argv: list[str]) -> int:
    import argparse
    import subprocess
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(99999)"])
    try:
        time.sleep(a.seconds)
    except KeyboardInterrupt:
        pass
    finally:
        if child.poll() is None:
            child.terminate()
    return 0


if __name__ == "__main__":
    cli()
