#!/usr/bin/env python
"""Alias (zgodnosc wsteczna): logika przeniesiona do eyes/cmd_measure.py,
wywolywana tez jako `python -m eyes measure`. Ten skrypt istnieje wylacznie
dla zapisanych starych komend - parsuje te same argumenty i woła te sama
funkcje `main()`.

measure.py --project "Nazwa" --files <plik1> <plik2> ...
           [--out X] [--config X] [--lut X] [--no-gpu] [--force]
           [--window-start 5 --window-len 20]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eyes.cmd_measure import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
