"""MCP server (stdio) exposing sonny-eyes measurement tools to an LLM client.

Uruchamiane przez `python -m eyes mcp` (eyes/cli.py). Konfiguracja identyczna
jak CLI: `EYES_CONFIG` / `EYES_OUT` (zmienne srodowiskowe), `config.toml`
obok repo, w ostatecznosci domyslne (patrz eyes/config.py) - narzedzia
tutaj wolaja `load_config()` bez jawnej sciezki, wiec dziedzicza dokladnie
te sama kolejnosc nadpisan.

Ten repo pinuje `mcp==2.1.1` (requirements.lock). W tej wersji pakietu
klasa FastMCP ze starego mcp 1.x zostala zastapiona przez `MCPServer`
(`mcp.server.fastmcp` przy imporcie rzuca ModuleNotFoundError z gotowa
instrukcja migracji) - stad ten modul uzywa `mcp.server.mcpserver.MCPServer`,
nie FastMCP. API dekoratora `.tool()` i `.run(transport="stdio")` jest
rownowazne temu, co mialoby FastMCP w mcp 1.x.

Bezpieczenstwo stdout: `measure_clip`/`review_page` woluja w tym samym
procesie funkcje CLI (`cmd_measure.main`, `cmd_review.main`), ktore drukuja
linie postepu przez `print()` (mysla, ze pisza do terminala). `mcp.server.
stdio.stdio_server()` na czas serwowania przekierowuje deskryptor 1 na
stderr na poziomie OS (patrz jego docstring w tym pakiecie) - ale to chroni
tylko wydruki faktycznie ZAPISANE na fd w tym oknie. Zaobserwowane empirycznie
(pierwsza wersja tego modulu): print() z process_file() zostaje w buforze
sys.stdout (pipe = block-buffered, nie liniowo), a jego faktyczny flush
potrafi nastapic PO tym, jak stdio_server() juz przywrocil prawdziwy fd 1 -
wtedy zalegly tekst trafia na wire jako smiec miedzy sesjami i psuje
nastepny odczyt JSON-RPC po stronie klienta (test_mcp.py to zlapal - patrz
`_quiet_stdout` nizej). Rozwiazanie: przy wywolaniach w tym samym procesie
`sys.stdout` jest podmieniany na `io.StringIO()` na czas wywolania, wiec te
wydruki nigdy nie dotykaja zadnego prawdziwego deskryptora.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from eyes import cmd_measure, cmd_review  # noqa: E402
from eyes import keys as keys_mod  # noqa: E402
from eyes import probe as probe_mod  # noqa: E402
from eyes import runner as runner_mod  # noqa: E402
from eyes.config import Config, ConfigError, load_config  # noqa: E402

server = MCPServer("sonny-eyes")


def _cfg() -> Config:
    """load_config() bez jawnej sciezki - ta sama kolejnosc nadpisan co CLI
    (CLI-argumentow tu nie ma, wiec liczy sie EYES_CONFIG/EYES_OUT env,
    potem config.toml obok repo, potem domyslne). Zly config.toml (zly TOML
    albo stare klucze) daje ConfigError - zamieniamy na ToolError, zeby
    model dostal czytelny komunikat zamiast tracebacku."""
    try:
        return load_config(None, overrides=None)
    except ConfigError as e:
        raise ToolError(str(e)) from e


def _strip_profiles(report: dict) -> dict:
    """Kopia raportu bez duzych tablic co-sekunde (ruch.profil,
    tonalnosc.profil) - agregaty (percentyle, mediany, klasa, jitter_rms_pct
    itd.) zostaja. Uzywane przez compact=True w measure_clip/get_report."""
    r = copy.deepcopy(report)
    ruch = r.get("ruch")
    if isinstance(ruch, dict):
        ruch.pop("profil", None)
    tonalnosc = r.get("tonalnosc")
    if isinstance(tonalnosc, dict):
        tonalnosc.pop("profil", None)
    return r


@contextlib.contextmanager
def _quiet_stdout():
    """Podmienia sys.stdout na io.StringIO() na czas wywolania funkcji CLI
    w tym samym procesie (cmd_measure.main, cmd_review.main) - patrz docstring
    modulu. Nie loguje przechwyconej tresci (i tak jest to gadanie do
    terminala, nie dane wyniku), tylko ja odrzuca."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def _resolve_existing(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise ToolError(f"clip not found: {path}")
    return p.resolve()


@server.tool()
def probe_clip(path: str) -> dict:
    """Read a clip's container/stream metadata with ffprobe - codec, resolution,
    frame rate (both the declared and the average), pixel format, color range/
    transfer/primaries, duration and frame count, plus the camera guessed from
    the filename (Fuji/GoPro/unknown, from the file's naming convention).

    Runs in well under a second (a single ffprobe call, no decoding). Use it
    for a quick sanity check on a clip - is this really 4K, what's the actual
    frame rate, is it the camera you expect - before committing to a full
    measure_clip call.
    """
    p = _resolve_existing(path)
    try:
        info = probe_mod.probe(str(p))
    except FileNotFoundError as e:
        raise ToolError(f"ffprobe not found in PATH ({e})") from e
    except RuntimeError as e:
        raise ToolError(str(e)) from e
    kamera, kamera_nieznana = keys_mod.detect_camera(p.name)
    info["kamera"] = kamera
    info["kamera_nieznana"] = kamera_nieznana
    return info


@server.tool()
def measure_clip(
    path: str,
    project: str = "default",
    force: bool = False,
    lut: str | None = None,
    compact: bool = False,
) -> dict:
    """Run the full perception measurement (ffmpeg decode + numpy/OpenCV metrics)
    on one clip and return the report exactly as written to disk, plus
    report_path/frames_dir/scopes_dir. Takes roughly 5-60 seconds depending on
    clip length and GPU availability - this is a synchronous, blocking call,
    not a quick lookup. If a report already exists for this clip/project and
    force=False, the existing report is returned unchanged with cached=true
    and nothing is re-measured.

    All numbers come from measuring pixels with ffmpeg/numpy/OpenCV - never
    from looking at a thumbnail. The report's werdykty field is always null:
    judging whether a clip is usable is a human call, this tool only measures.
    progi_prowizoryczne (the thresholds behind flagi_prowizoryczne and
    ruch.klasa) are provisional, hand-calibrated on a handful of clips - state
    them as "the current provisional threshold", not as settled fact. Pass
    compact=True to drop the large per-second arrays (ruch.profil,
    tonalnosc.profil) and keep only the aggregates - much cheaper in tokens
    when you only need the summary numbers.
    """
    p = _resolve_existing(path)
    cfg = _cfg()
    id_ = keys_mod.compute_id(p, [p])
    report_path = cfg.reports_dir(project) / f"{id_}.json"
    cache_root = Path(cfg.cache_root)
    frames_dir = cache_root / project / id_ / "frames"
    scopes_dir = cache_root / project / id_ / "scopes"

    cached = report_path.exists() and not force
    if not cached:
        argv = ["--project", project, "--files", str(p)]
        if force:
            argv.append("--force")
        if lut:
            argv += ["--lut", lut]
        with _quiet_stdout():
            rc = cmd_measure.main(argv)
        if rc != 0 or not report_path.exists():
            raise ToolError(
                f"measurement failed for {path} (exit={rc}; see _log.jsonl under "
                f"{cache_root / project} for the error entry)"
            )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if compact:
        report = _strip_profiles(report)
    report["cached"] = cached
    report["report_path"] = str(report_path)
    report["frames_dir"] = str(frames_dir)
    report["scopes_dir"] = str(scopes_dir)
    return report


@server.tool()
def get_report(project: str, id: str, compact: bool = False) -> dict:  # noqa: A002 - "id" is the spec'd param name
    """Load one already-measured report from disk by project and id (the clip's
    filename stem, e.g. "DSCF3236") without re-measuring anything. Instant -
    just reads and parses a JSON file. Raises a readable error (not a
    traceback) when no report exists for that project/id yet; use measure_clip
    first. Pass compact=True to drop the large per-second arrays (ruch.profil,
    tonalnosc.profil) and keep only the aggregates.
    """
    cfg = _cfg()
    report_path = cfg.reports_dir(project) / f"{id}.json"
    if not report_path.exists():
        raise ToolError(f'no report for project "{project}", id "{id}" (looked at {report_path})')
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if compact:
        report = _strip_profiles(report)
    return report


@server.tool()
def list_reports(project: str) -> list[dict]:
    """List every already-measured report in a project as a short summary row
    each: id, plik (source filename), kamera, czas_s (clip duration), ruch_klasa
    (camera-motion classification list), flagi_prowizoryczne (the active
    provisional flags, if any) and pomiar_bez_lut (true when measured without a
    LUT). No profiles, no scope images - use get_report for the full report of
    one clip. Fast (just reads small JSON files); an empty/missing project
    folder returns an empty list, not an error.
    """
    cfg = _cfg()
    reports_dir = cfg.reports_dir(project)
    if not reports_dir.exists():
        return []
    rows = []
    for p in sorted(reports_dir.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        zrodlo = r.get("zrodlo") or {}
        ruch = r.get("ruch") or {}
        niepewnosc = r.get("niepewnosc") or {}
        rows.append({
            "id": r.get("id"),
            "plik": zrodlo.get("plik"),
            "kamera": zrodlo.get("kamera"),
            "czas_s": zrodlo.get("czas_s"),
            "ruch_klasa": ruch.get("klasa"),
            "flagi_prowizoryczne": r.get("flagi_prowizoryczne") or [],
            "pomiar_bez_lut": niepewnosc.get("pomiar_bez_lut"),
        })
    return rows


@server.tool()
def batch_start(
    project: str,
    folders: list[str],
    porcja: str | None = None,
    limit: int | None = None,
    force: bool = False,
    no_gpu: bool = False,
) -> dict:
    """Start measuring every camera clip under one or more folders (recursively)
    as a detached background process, and return immediately with the
    _runner.json contents (pid, cmd, log path, postep path) - it does NOT wait
    for the batch to finish, which can take minutes to hours. Poll progress
    with batch_status afterwards. Raises a readable error if a batch is
    already running for this project - stop it first with batch_stop, or wait
    for it to finish.
    """
    cfg = _cfg()
    cache_root = Path(cfg.cache_root)
    argv = ["--project", project]
    for f in folders:
        argv += ["--folder", f]
    if porcja:
        argv += ["--porcja", porcja]
    if force:
        argv.append("--force")
    if limit is not None:
        argv += ["--limit", str(limit)]
    if no_gpu:
        argv.append("--no-gpu")

    cmd = [sys.executable, "-m", "eyes", "batch", *argv]
    info = runner_mod.start_detached(
        cmd, project=project, cache_root=cache_root, porcja=porcja or (Path(folders[0]).name if folders else None),
    )
    if info is None:
        raise ToolError(f'a batch is already running for project "{project}" - see batch_status/batch_stop')
    return info


@server.tool()
def batch_status(project: str) -> dict:
    """Report whether a detached batch is running for this project and how far
    it got - the same data as `python -m eyes status --json`: the runner info
    (pid, alive, start time), and _postep.json (status, files done/total,
    ok/skipped/duplicate/error counts, eta, last file processed). When no
    batch was ever started for this project, runner and postep are both null
    - that is a normal, expected result, not an error.
    """
    cfg = _cfg()
    return runner_mod.get_status(project, Path(cfg.cache_root))


@server.tool()
def batch_stop(project: str) -> dict:
    """Kill a running detached batch for this project (the whole process tree,
    ffmpeg included) and mark its progress file interrupted. Returns
    {"code", "message", "postep"} - code 0 covers both "stopped it" and
    "nothing was running" (that is not an error, just a status). Instant
    (terminate, then a few seconds' grace, then kill if needed).
    """
    cfg = _cfg()
    cache_root = Path(cfg.cache_root)
    code, msg = runner_mod.stop(project, cache_root)
    postep = runner_mod.read_json(runner_mod.postep_path(cache_root, project))
    return {"code": code, "message": msg, "postep": postep}


@server.tool()
def review_page(project: str, compact: bool = True) -> dict:
    """Generate the HTML review page (thumbnails, numbers, flags, sortable/
    filterable grid) for every measured clip in a project, and return
    {"path": <written HTML file>, "reports": <how many clips are on it>}. This
    is for a human to open in a browser - it does not return the page content
    itself. compact=True (the default) uses small JPEGs instead of full PNGs
    so the page stays well under typical size limits; set it False only when
    you specifically need full-resolution images. Takes a couple seconds per
    dozen clips (mostly image re-encoding).
    """
    cfg = _cfg()
    argv = ["--project", project]
    if compact:
        argv.append("--compact")
    with _quiet_stdout():
        rc = cmd_review.main(argv)
    if rc != 0:
        raise ToolError(f'review page generation failed for project "{project}" (exit={rc})')
    out_path = Path(cfg.cache_root) / project / "_przeglad.html"
    n_reports = len(list(cfg.reports_dir(project).glob("*.json")))
    return {"path": str(out_path), "reports": n_reports}


if __name__ == "__main__":
    server.run(transport="stdio")
