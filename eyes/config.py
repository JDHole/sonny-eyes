"""Wczytanie config.toml (opcjonalny) + nadpisania z CLI/env.

Kolejnosc nadpisan (pierwsze wygrywa): CLI (`overrides`) > zmienne
srodowiskowe (`EYES_OUT`, `EYES_CONFIG`) > config.toml obok repo (jesli
istnieje) > domyslne. Brak config.toml NIE jest bledem - narzedzie dziala
od razu z samymi domyslnymi (`out_root = "./eyes-out"` wzgledem cwd).

Stare klucze sprzed publicznej wersji (`vault`, `production_root`,
`lut_fuji`) daja czytelny ConfigError z instrukcja migracji zamiast
tracebacku - patrz config.example.toml w repo.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_OUT_ROOT = "./eyes-out"
OLD_KEYS = ("vault", "production_root", "lut_fuji")

MIGRATION_MSG = (
    "config.toml uzywa nieaktualnych kluczy sprzed wersji publicznej: {keys}. "
    "Migracja: usun 'vault' / 'production_root' / 'lut_fuji' i dodaj (wszystkie "
    "opcjonalne) 'out_root', 'cache_root', 'reports_root' (szablon ze "
    "znacznikiem {{project}}) oraz tabele [lut] z mapowaniem nazwa_kamery = "
    "\"sciezka/do/pliku.cube\". Wzor: config.example.toml w tym repo."
)


class ConfigError(Exception):
    """Czytelny blad configu (zamiast tracebacku z KeyError/tomllib)."""


@dataclass
class Config:
    out_root: str
    cache_root: str
    reports_root: str  # szablon ze znacznikiem {project}
    lut: dict[str, str] = field(default_factory=dict)  # kamera -> sciezka .cube

    def reports_dir(self, project: str) -> Path:
        """Katalog raportow danego projektu (formatuje szablon reports_root)."""
        return Path(self.reports_root.format(project=project))

    def color_dir(self, project: str) -> Path:
        """Katalog nadrzedny nad reports_dir - miejsce na werdykty.json,
        kasacje duplikatow itp. (u Kuby to .../Color; domyslnie po prostu
        {cache_root}/{project})."""
        return self.reports_dir(project).parent


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"config.toml ma zly skladnie TOML ({path}): {e}") from e


def load_config(config_path: Path | str | None = None, overrides: dict | None = None) -> Config:
    """Czyta config (jesli istnieje) i sklada Config wg kolejnosci nadpisan.

    config_path: jawna sciezka do pliku toml (np. --config z CLI albo test).
        None -> szuka w EYES_CONFIG (zmienna srodowiskowa), inaczej
        config.toml obok repo. W kazdym przypadku brak pliku pod finalna
        sciezka NIE jest bledem - po prostu brak danych z pliku.
    overrides: dict z kluczami out_root/cache_root/reports_root - wartosci
        None sa ignorowane (nie nadpisuja). To jest warstwa CLI (najwyzszy
        priorytet).
    """
    overrides = overrides or {}

    if config_path is None:
        env_cfg = os.environ.get("EYES_CONFIG")
        config_path = Path(env_cfg) if env_cfg else (REPO_ROOT / "config.toml")
    else:
        config_path = Path(config_path)

    data: dict = _read_toml(config_path) if config_path.exists() else {}

    old_present = [k for k in OLD_KEYS if k in data]
    if old_present:
        raise ConfigError(MIGRATION_MSG.format(keys=", ".join(old_present)))

    out_root = (
        overrides.get("out_root")
        or os.environ.get("EYES_OUT")
        or data.get("out_root")
        or DEFAULT_OUT_ROOT
    )
    cache_root = overrides.get("cache_root") or data.get("cache_root") or out_root
    reports_root = (
        overrides.get("reports_root")
        or data.get("reports_root")
        or f"{cache_root}/{{project}}/reports"
    )

    lut = data.get("lut", {}) or {}
    if not isinstance(lut, dict) or not all(isinstance(v, str) for v in lut.values()):
        raise ConfigError(
            "[lut] w config.toml musi byc tabela 'nazwa_kamery = \"sciezka.cube\"' "
            "(klucz jak w polu zrodlo.kamera raportu, np. 'fuji')."
        )

    return Config(out_root=str(out_root), cache_root=str(cache_root), reports_root=str(reports_root), lut=dict(lut))
