#!/usr/bin/env python
"""Alias (zgodnosc wsteczna): logika przeniesiona do eyes/cmd_profile.py,
wywolywana tez jako `python -m eyes profile`. Ten skrypt istnieje wylacznie
dla zapisanych starych komend - parsuje te same argumenty i woła te sama
funkcje `main()`.

przebieg.py --project "Nazwa" [--ids ID1 ID2 ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes.cmd_profile import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
