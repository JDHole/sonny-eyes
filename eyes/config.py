"""Wczytanie config.toml + nadpisania z CLI."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    vault: str
    production_root: str
    cache_root: str
    lut_fuji: str


def load_config(config_path: Path, overrides: dict | None = None) -> Config:
    """Czyta config.toml spod config_path, opcjonalnie nadpisuje pola.

    overrides: dict z kluczami vault/production_root/cache_root/lut_fuji;
    wartosci None sa ignorowane (nie nadpisuja).
    """
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
    return Config(
        vault=data["vault"],
        production_root=data["production_root"],
        cache_root=data["cache_root"],
        lut_fuji=data["lut_fuji"],
    )
