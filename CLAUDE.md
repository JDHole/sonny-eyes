# CLAUDE.md - sonny-eyes

Narzedzie pomiaru percepcyjnego ujec (raport ujecia v0). Zasady sesji:

1. Zapisuj TYLKO do: tego repo, `cache_root` (`Cache/percepcja/`) i
   `{vault}/.../Color/reports/` danego projektu. Nic wiecej.
2. Zero kasowania/przenoszenia innych plikow (`ShadowNotes/`,
   `shot_inventory.json`, zrodlowe wideo - nietykalne).
3. Zero DaVinci Resolve, zero renderow/eksportow - tylko pomiar.
4. `pip install` zakazane - lock ma wszystko. Brak pakietu = stop + raport.
5. Klucz pliku = stem nazwy. Kolizja stem -> `stem@folder`.
6. Raporty JSON sa regenerowalne - kasowanie i ponowny pomiar jest ok.
7. Po edycji `.py`: `python -m py_compile` przed uznaniem za gotowe.
8. Commity robi wlasciciel repo, nie sesja.
