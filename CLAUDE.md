# CLAUDE.md - sonny-eyes

Narzedzie pomiaru percepcyjnego ujec (raport ujecia v0). Zasady sesji:

1. Zapisuj TYLKO do: tego repo, `out_root`/`cache_root` (u Kuby:
   `Cache/percepcja/`) i `reports_root` danego projektu (u Kuby: folder
   `Color/reports/` w vaultcie, konfigurowalny szablon ze znacznikiem
   `{project}` - patrz `eyes/config.py` i `config.example.toml`). Nic wiecej.
2. Zero kasowania/przenoszenia innych plikow (`ShadowNotes/`,
   `shot_inventory.json`, zrodlowe wideo - nietykalne).
3. Zero DaVinci Resolve, zero renderow/eksportow - tylko pomiar.
4. `pip install` zakazane - lock ma wszystko. Brak pakietu = stop + raport.
5. Klucz pliku = stem nazwy. Kolizja stem -> `stem@folder`.
6. Raporty JSON sa regenerowalne - kasowanie i ponowny pomiar jest ok.
7. Po edycji `.py`: `python -m py_compile` przed uznaniem za gotowe.
8. Commity robi wlasciciel repo, nie sesja.
9. `config.toml` (fizyczny plik ze sciezkami Kuby) jest w `.gitignore` -
   nie wchodzi do repo, nie commituj go i nie kasuj. Wzor do repo to
   `config.example.toml` (komentarze po angielsku, bez prawdziwych
   sciezek). Brak `config.toml` nie jest bledem - narzedzie dziala wtedy
   na samych domyslnych (`./eyes-out`).
