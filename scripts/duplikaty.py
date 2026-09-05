"""Lista duplikatow z logu przemialu + weryfikacja pelnym hashem. NIGDY nic nie kasuje.

Uzycie (venv):
  scripts/duplikaty.py --project "Canarian Tweety EP03" [--verify]
Czyta {cache_root}/{P}/_log.jsonl (wpisy status=duplikat z measure.py: plik pominiety + duplikat_of).
--verify liczy sha1 CALEGO pliku dla obu stron pary (wolne: czyta wszystkie bajty) i oznacza pary
"identyczne" / "ROZNE" (rozne = tylko pierwsze 4 MB sie zgadzaly, taki plik NIE jest kandydatem do kasacji).
Pisze: {vault}/40_Pracownie/Analog Studio/Projekty/{P}/Color/kasacja_duplikaty.json i .md (lista dla Kuby).
Kasacja to decyzja Kuby, poza tym skryptem.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from eyes.config import load_config  # noqa: E402


def sha1_full(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--vault", default=None)
    ap.add_argument("--cache-root", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(REPO_ROOT / "config.toml", overrides={"vault": a.vault, "cache_root": a.cache_root})
    log = Path(cfg.cache_root) / a.project / "_log.jsonl"
    color = Path(cfg.vault) / "40_Pracownie" / "Analog Studio" / "Projekty" / a.project / "Color"
    if not log.exists():
        print(f"brak logu: {log}")
        return 1

    pary: dict[str, dict] = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("status") != "duplikat":
            continue
        kopia = e.get("sciezka_rel") or ""
        pary[kopia] = {"id": e.get("id"), "kopia": kopia, "oryginal": e.get("duplikat_of"), "hash_4mb": e.get("hash_4mb"), "data_logu": e.get("data")}

    wyniki = []
    razem_b = 0
    for kopia, e in sorted(pary.items()):
        pk, po = Path(kopia), Path(e["oryginal"] or "")
        istnieje = pk.exists() and po.exists()
        rozmiar = pk.stat().st_size if pk.exists() else None
        rec = {**e, "istnieje_para": istnieje, "rozmiar_b": rozmiar, "rozmiar_zgodny": (istnieje and rozmiar == po.stat().st_size), "pelny_hash": None, "identyczne": None}
        if a.verify and istnieje and rec["rozmiar_zgodny"]:
            hk, ho = sha1_full(pk), sha1_full(po)
            rec["pelny_hash"] = hk
            rec["identyczne"] = hk == ho
            print(f"{e['id']}: {'identyczne' if rec['identyczne'] else 'ROZNE'} ({(rozmiar or 0)/1e9:.2f} GB)", flush=True)
        if rec["rozmiar_zgodny"] and rec["identyczne"] is not False and rozmiar:
            razem_b += rozmiar
        wyniki.append(rec)

    color.mkdir(parents=True, exist_ok=True)
    out = {"schema": "kasacja-duplikaty/0.1", "projekt": a.project, "data": dt.datetime.now().isoformat(timespec="minutes"), "zweryfikowano_pelnym_hashem": a.verify, "par": len(wyniki), "do_odzyskania_b": razem_b, "uwaga": "Lista kandydatow. Kasacja wylacznie decyzja Kuby. Kopia = plik do usuniecia, oryginal zostaje (pierwszy po posortowaniu sciezek).", "pary": wyniki}
    (color / "kasacja_duplikaty.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    ident = sum(1 for w in wyniki if w["identyczne"] is True)
    rozne = [w for w in wyniki if w["identyczne"] is False]
    niezw = sum(1 for w in wyniki if w["identyczne"] is None)
    md = [f"# Kasacja, krok 1: identyczne kopie ({a.project})", "",
          f"Stan: {out['data']}. Par: {len(wyniki)}. Zweryfikowane pełnym hashem: {'tak' if a.verify else 'nie'} (identyczne {ident}, RÓŻNE {len(rozne)}, niezweryfikowane {niezw}).",
          f"Do odzyskania po kasacji kopii: **{razem_b/1e9:.1f} GB**.", "",
          "Zasada: kopia to plik do usunięcia, oryginał zostaje. Lista to propozycja Sonny'ego, kasacja wyłącznie po słowie Kuby. Pliki RÓŻNE (zgodne tylko w pierwszych 4 MB) NIE są kandydatami.", "",
          "| id | kopia (do usunięcia) | oryginał (zostaje) | GB | pełny hash |", "|---|---|---|---|---|"]
    for w in wyniki:
        st = "identyczne" if w["identyczne"] else ("RÓŻNE" if w["identyczne"] is False else "niezweryfikowane")
        md.append(f"| {w['id']} | {w['kopia']} | {w['oryginal']} | {(w['rozmiar_b'] or 0)/1e9:.2f} | {st} |")
    (color / "kasacja_duplikaty.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"par: {len(wyniki)} | identyczne: {ident} | ROZNE: {len(rozne)} | niezweryfikowane: {niezw} | do odzyskania: {razem_b/1e9:.1f} GB | -> {color / 'kasacja_duplikaty.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
