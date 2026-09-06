"""Test dymny runnera (bramka Z3). Dziala jako zwykly skrypt (bez pytest):

    .venv/Scripts/python.exe tests/test_runner.py

Dwie czesci:
1. Sztuczne zadanie (`python -m eyes _sleep --detach`, podkomenda ukryta,
   tylko do tego testu): start --detach, status pokazuje alive, drugi
   --detach na tym samym projekcie odmawia (exit 3), stop ubija CALE
   drzewo (rodzic + dziecko), _postep.json sztuczny z "w toku" po stopie
   ma "przerwany", brak zywego procesu po stopie = stop nie jest bledem.
2. Realny `python -m eyes batch --detach` na 2 klipach z folderu Kuby
   (znaleziony przez tests/test_smoke.py: 100_FUJI z Dzien 7) - status co
   2 s do konca, sprawdza _postep.json "zakonczony" i _batch.log z UTF-8
   po polsku.

Wymaga psutil (patrz requirements.lock) - instalowany specjalnie pod ten
runner (wyjatek od "pip install zakazane" tej sesji).
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import subprocess
import tempfile
import time
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes import runner as runner_mod  # noqa: E402

PY = sys.executable
FOLDER_2_3_KLIPOW = (
    r"C:\Users\jdziu\JDHole Production\VIdeo\Vlog\#39-42 Canarian Tweety Series\Dzień 7\100_FUJI"
)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def run_eyes(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, "-m", "eyes", *args],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )


def czesc_1_sleep_i_stop(tmp: Path) -> None:
    project = "TestRunnerSleep"
    out = str(tmp / "sleep_out")

    # --- start --detach ---
    r = run_eyes(["_sleep", "--project", project, "--seconds", "40", "--out", out, "--detach"])
    check(r.returncode == 0, f"_sleep --detach exit={r.returncode} stderr={r.stderr!r}")
    try:
        info = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        check(False, f"_sleep --detach nie wypisal poprawnego JSON-a: {e} (stdout={r.stdout!r})")
        return
    pid = info.get("pid")
    check(isinstance(pid, int) and psutil.pid_exists(pid), f"_sleep --detach: pid {pid} nie istnieje zaraz po starcie")

    time.sleep(1.5)  # daj dziecku (python -c time.sleep) czas na spawn

    parent_alive_before = psutil.pid_exists(pid)
    child_pids: list[int] = []
    if parent_alive_before:
        try:
            child_pids = [c.pid for c in psutil.Process(pid).children(recursive=True)]
        except psutil.NoSuchProcess:
            pass
    check(len(child_pids) >= 1, f"_sleep: brak spodziewanego dziecka (python -c time.sleep) pod pid {pid}")

    # --- status pokazuje alive ---
    st = runner_mod.get_status(project, Path(out))
    check(st["alive"] is True, f"status.alive={st['alive']} tuz po starcie --detach")

    # --- drugi --detach na tym samym projekcie odmawia (exit 3) ---
    r2 = run_eyes(["_sleep", "--project", project, "--seconds", "40", "--out", out, "--detach"])
    check(r2.returncode == 3, f"drugi _sleep --detach przy zywym procesie: exit={r2.returncode} (oczekiwano 3)")

    # --- sztuczny _postep.json "w toku" (stop powinien go zamknac) ---
    postep_path = runner_mod.postep_path(Path(out), project)
    postep_path.parent.mkdir(parents=True, exist_ok=True)
    postep_path.write_text(json.dumps({"schema": "postep-przemialu/0.1", "status": "w toku", "koniec": None, "aktualizacja": None}), encoding="utf-8")

    # --- stop ubija cale drzewo ---
    r3 = run_eyes(["stop", "--project", project, "--out", out])
    check(r3.returncode == 0, f"stop exit={r3.returncode} stderr={r3.stderr!r}")

    time.sleep(1.0)
    check(not psutil.pid_exists(pid), f"stop: rodzic {pid} nadal zyje")
    for cpid in child_pids:
        check(not psutil.pid_exists(cpid), f"stop: dziecko {cpid} nadal zyje (drzewo nie zostalo ubite)")

    postep_po = json.loads(postep_path.read_text(encoding="utf-8"))
    check(postep_po.get("status") == "przerwany", f"_postep.json po stop: status={postep_po.get('status')!r}, oczekiwano 'przerwany'")
    check(postep_po.get("koniec") is not None, "_postep.json po stop: koniec nadal None")

    # --- stop bez zywego procesu = exit 0, nie blad ---
    r4 = run_eyes(["stop", "--project", project, "--out", out])
    check(r4.returncode == 0, f"stop na juz-zatrzymanym projekcie: exit={r4.returncode} (oczekiwano 0)")


def czesc_2_realny_batch(tmp: Path) -> None:
    project = "Canarian Tweety EP03"
    out = str(tmp / "batch_out")
    folder = Path(FOLDER_2_3_KLIPOW)
    if not folder.is_dir():
        check(False, f"folder testowy nie istnieje, pomijam czesc 2: {folder}")
        return

    r = run_eyes([
        "batch", "--project", project, "--folder", str(folder),
        "--limit", "2", "--force", "--out", out, "--detach",
    ])
    check(r.returncode == 0, f"batch --detach exit={r.returncode} stderr={r.stderr!r}")
    try:
        info = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        check(False, f"batch --detach nie wypisal poprawnego JSON-a: {e} (stdout={r.stdout!r})")
        return
    pid = info.get("pid")

    postep_path = runner_mod.postep_path(Path(out), project)
    deadline = time.time() + 15 * 60  # pomiar 2 klipow 4K - budzet z zapasem
    status_koncowy = None
    while time.time() < deadline:
        st = runner_mod.get_status(project, Path(out))
        postep = st.get("postep") or {}
        status_koncowy = postep.get("status")
        if status_koncowy in ("zakonczony", "zakonczony z bledami", "przerwany"):
            break
        if not st["alive"] and status_koncowy not in ("zakonczony", "zakonczony z bledami"):
            # proces padl bez zamkniecia postepu - nie czekaj w nieskonczonosc
            break
        time.sleep(2)

    check(status_koncowy == "zakonczony", f"_postep.json status koncowy={status_koncowy!r}, oczekiwano 'zakonczony'")
    check(not psutil.pid_exists(pid) or not runner_mod.is_alive(info), f"proces batch {pid} nadal wyglada na zywy po zakonczeniu")

    log_path = runner_mod.batch_log_path(Path(out), project)
    check(log_path.exists(), f"brak _batch.log: {log_path}")
    if log_path.exists():
        tresc = log_path.read_text(encoding="utf-8")
        check("przemial" in tresc, "_batch.log: brak spodziewanego polskiego tekstu 'przemial' (UTF-8 zle zdekodowany?)")
        check(len(tresc.strip()) > 0, "_batch.log jest pusty")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="eyes_test_runner_") as tmp_s:
        tmp = Path(tmp_s)
        czesc_1_sleep_i_stop(tmp)
        czesc_2_realny_batch(tmp)

    if failures:
        print(f"TEST_RUNNER: FAIL ({len(failures)} problemow)")
        for f in failures:
            print(" - " + f)
        return 1

    print("TEST_RUNNER: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
