"""Alias (zgodnosc wsteczna): logika przeniesiona do eyes/cmd_dupes.py,
wywolywana tez jako `python -m eyes dupes`. Ten skrypt istnieje wylacznie
dla zapisanych starych komend - parsuje te same argumenty i woła te sama
funkcje `main()`.

duplikaty.py --project "Canarian Tweety EP03" [--verify]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eyes.cmd_dupes import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
