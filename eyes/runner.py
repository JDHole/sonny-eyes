"""Runner: proces odczepiony (`batch --detach` / testowe `_sleep --detach`),
zabijanie calego drzewa procesow (`stop`), polaczony status (`status`).

Wymaga psutil (patrz requirements.lock/requirements.txt - instalowany
wylacznie dla tej funkcji, kanon "pip install zakazane" repo uchylony na
czas tej sesji wg CLAUDE.md).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import psutil

RUNNER_SCHEMA = "runner/0.1"


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict) -> None:
    """Zapis atomowy: plik tymczasowy + os.replace (jak _postep.json przemialu)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def runner_path(cache_root: Path, project: str) -> Path:
    return Path(cache_root) / project / "_runner.json"


def postep_path(cache_root: Path, project: str) -> Path:
    return Path(cache_root) / project / "_postep.json"


def batch_log_path(cache_root: Path, project: str) -> Path:
    return Path(cache_root) / project / "_batch.log"


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _cmdline_ours(p: psutil.Process) -> bool:
    """True gdy cmdline procesu wyglada na nasz (`python -m eyes ... batch|_sleep ...`) -
    zabezpieczenie przed zrecyklowanym PID (patrz README/zadanie: PID moze zostac
    przydzielony calkiem innemu procesowi po ponownym starcie systemu)."""
    try:
        cl = p.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    joined = " ".join(cl).lower()
    return "eyes" in joined and ("batch" in joined or "_sleep" in joined)


def is_alive(runner_info: dict) -> bool:
    pid = runner_info.get("pid")
    if not pid or not psutil.pid_exists(pid):
        return False
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    return _cmdline_ours(p)


def start_detached(cmd: list[str], *, project: str, cache_root: Path, porcja: str | None = None) -> dict | None:
    """Uruchamia `cmd` (pelna komenda, np. [sys.executable, "-m", "eyes", "batch", ...])
    jako proces odczepiony od terminala (Windows: CREATE_NEW_PROCESS_GROUP |
    DETACHED_PROCESS; POSIX: start_new_session). stdout+stderr trafiaja (append,
    UTF-8) do {cache_root}/{project}/_batch.log, stdin DEVNULL. Zwraca None (bez
    startu) gdy _runner.json projektu wskazuje juz zywy proces."""
    cache_root = Path(cache_root)
    rp = runner_path(cache_root, project)
    existing = read_json(rp)
    if existing and is_alive(existing):
        return None

    log_path = batch_log_path(cache_root, project)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "a", encoding="utf-8")

    popen_kwargs: dict = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=log_f, stderr=log_f,
            close_fds=True, **popen_kwargs,
        )
    finally:
        log_f.close()

    info = {
        "schema": RUNNER_SCHEMA,
        "pid": proc.pid,
        "cmd": cmd,
        "start": _now(),
        "project": project,
        "porcja": porcja,
        "log": str(log_path),
        "postep": str(postep_path(cache_root, project)),
    }
    _atomic_write_json(rp, info)
    return info


def get_status(project: str, cache_root: Path) -> dict:
    cache_root = Path(cache_root)
    runner_info = read_json(runner_path(cache_root, project))
    alive = bool(runner_info and is_alive(runner_info))
    postep = read_json(postep_path(cache_root, project))
    return {"project": project, "runner": runner_info, "alive": alive, "postep": postep}


def format_status_text(st: dict) -> str:
    runner_info, postep, alive = st["runner"], st["postep"], st["alive"]
    lines = [f"projekt: {st['project']}"]
    if runner_info is None:
        lines.append("runner: brak (nigdy nie odpalono --detach albo _runner.json zniknal)")
    else:
        lines.append(f"proces: pid={runner_info.get('pid')} alive={'tak' if alive else 'nie'} start={runner_info.get('start')}")
        if runner_info.get("stopped"):
            lines.append(f"zatrzymany: {runner_info['stopped']}")
    if postep is None:
        lines.append("postep: brak _postep.json")
    else:
        lines.append(f"status: {postep.get('status')}")
        lines.append(f"zrobione: {postep.get('zrobione')}/{postep.get('plikow')} (ok={postep.get('ok')} pominiete={postep.get('pominiete')} duplikaty={postep.get('duplikaty')} bledy={postep.get('bledy')})")
        if postep.get("eta_s") is not None:
            lines.append(f"eta: {postep['eta_s']} s (koniec ok. {postep.get('eta_koniec')})")
        ost = postep.get("ostatni")
        if ost:
            lines.append(f"ostatni: {ost.get('id')} ({ost.get('plik')}) -> {ost.get('status')}")
    return "\n".join(lines)


def stop(project: str, cache_root: Path) -> tuple[int, str]:
    """Ubija drzewo procesow (dzieci rekurencyjnie, potem rodzica): terminate ->
    5 s -> kill. Brak zywego procesu = (0, komunikat), NIE blad. Po ubiciu, jesli
    _postep.json ma status "w toku", ustawia "przerwany" (skrypt ubity
    SIGKILL/TerminateProcess nie zdazy sam zaktualizowac swojego postepu)."""
    cache_root = Path(cache_root)
    rp = runner_path(cache_root, project)
    runner_info = read_json(rp)
    if not runner_info or not is_alive(runner_info):
        return 0, f'brak zywego procesu dla projektu "{project}"'

    pid = runner_info["pid"]
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return 0, f"proces {pid} juz nie istnieje"

    procs = parent.children(recursive=True) + [parent]
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _gone, alive = psutil.wait_procs(procs, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=5)

    postep = read_json(postep_path(cache_root, project))
    if postep and postep.get("status") == "w toku":
        now = _now()
        postep["status"] = "przerwany"
        postep["koniec"] = now
        postep["aktualizacja"] = now
        _atomic_write_json(postep_path(cache_root, project), postep)

    runner_info["stopped"] = _now()
    _atomic_write_json(rp, runner_info)
    return 0, f'zatrzymano proces {pid} (projekt "{project}", zabito {len(procs)} proces(ow))'
