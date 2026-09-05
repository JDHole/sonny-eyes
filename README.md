# sonny-eyes

Pomiar percepcyjny ujec wideo (raport ujecia v0). Bierze plik kamery,
mierzy go ffmpegiem + numpy/OpenCV/scikit-image/colour-science na krotkim
oknie, zapisuje JSON z liczbami plus miniaturki i skopy PNG. Zero AI, zero
werdyktow - tylko liczby do dalszej analizy (przez Sonny'ego albo recznie).

Wersja v0: metryki tonalne/kolorystyczne/ostrosci/szumu/ruchu na pojedynczym
oknie klipu. Brak wykrywania ciec (`montaz.segmenty` jest puste - miejsce
na przyszlosc).

## Jak odpalic

```
.venv/Scripts/python.exe scripts/measure.py --project "Nazwa Projektu" --files sciezka1.mov sciezka2.mp4
```

Opcje: `--cache-root X`, `--vault X` (nadpisuja config.toml), `--no-gpu`
(wymusza dekodowanie CPU), `--force` (przelicza nawet gdy raport juz
istnieje), `--window-start 5 --window-len 20` (domyslne okno dla klipow
>=30s; krotsze klipy mierzone sa w calosci od 0).

Test dymny (bramka, bez pytest):

```
.venv/Scripts/python.exe tests/test_smoke.py
```

## Uklad danych

- Raport: `{vault}/40_Pracownie/Analog Studio/Projekty/{project}/Color/reports/{id}.json`
- Cache: `{cache_root}/{project}/{id}/frames/*.png`, `.../scopes/*.png`,
  `{cache_root}/{project}/_log.jsonl` (jedna linia JSON per klip per
  uruchomienie: id, status ok/pominieto/blad, czas, wersja metryk),
  `{cache_root}/_luts/` (kopie LUT-ow uzywanych do pomiaru, patrz nizej).
- `id` = nazwa pliku bez rozszerzenia (`DSCF3236`). Kolizja stem w jednej
  liscie `--files` -> `stem@nazwa_folderu_nadrzednego`. Identyczny
  `hash_4mb` (sha1 pierwszych 4 MB) jak wczesniejszy plik na liscie =
  duplikat tresci, pomijany (nie liczony drugi raz).
- Raporty sa regenerowalne: kasowanie pliku JSON i ponowne odpalenie
  `measure.py` (albo `--force`) odtwarza go od zera. Nic w tym repo nie
  jest zrodlem prawdy poza samymi klipami kamery.

## Znane pulapki (Windows / to srodowisko)

- **cp1252 na stdout.** Konsola Windows domyslnie nie potrafi wypisac
  polskich znakow w niektorych trybach. Kazdy skrypt wola na starcie
  `sys.stdout.reconfigure(encoding="utf-8")` (i stderr). Pliki zawsze
  `encoding="utf-8"`.
- **Znak `#` i spacje w sciezkach** (np. folder `#39-42 Canarian Tweety
  Series`). Dziala bez dodatkowego escapowania, bo wszystkie wywolania
  ffmpeg/ffprobe ida przez `subprocess.run` z lista argumentow (bez shell),
  wiec Windows dostaje kazdy argument jako oddzielny token.
- **LUT w filtrze `lut3d` i dwukropek dysku.** Bezposrednie wstawienie
  sciezki Windows (`C:/...`) jako wartosci opcji `file=` w `-vf` psuje
  parser filtergraphu tego builda ffmpeg (8.0.1) - i to niezaleznie od
  tego, czy dwukropek jest escapowany (`\:`) czy wartosc jest w cudzyslowie
  (`'...'`), parser i tak gubi sie na literze dysku. Dziala tylko obejscie:
  LUT jest kopiowany raz do `{cache_root}/_luts/`, a ffmpeg jest odpalany
  z `cwd` ustawionym na ten katalog i referencja do LUT-a to sama nazwa
  pliku (bez dwukropka w ogole). Patrz `eyes/decode.py:ensure_lut_cached`.
- **`vectorscope` a `waveform`.** `waveform` dziala wprost na rgb24;
  `vectorscope` w tym buildzie ffmpeg wymaga jawnego `format=yuv420p`
  bezposrednio przed filtrem, inaczej ffmpeg zglasza "could not choose
  their formats" i nie potrafi otworzyc enkodera PNG.
- **Kolejnosc filtrow fps vs lut3d/scale.** `lut3d` (interpolacja 3D) jest
  drogi na pelnej rozdzielczosci 4K. Filtr `fps=N` (odrzucanie klatek) idzie
  w lancuchu PRZED `lut3d`/`scale`, zeby drogie przeliczenie dostawaly tylko
  faktycznie probkowane klatki, a nie kazda zdekodowana klatke zrodla.
  Wynik pikselowy jest identyczny (operacje sa per-klatka), tylko szybszy.
- **GPU (`-hwaccel cuda`) z fallbackiem.** Kazde wywolanie ffmpeg probuje
  najpierw `-hwaccel cuda`; jesli ffmpeg zwroci kod bledu (np. brak
  sterownika, niewspierany kodek), automatyczny retry bez hwaccel na CPU.
  `niepewnosc.gpu_fallback_cpu` w raporcie mowi, czy to sie zdarzylo.
  Realny zysk z GPU w v0 jest umiarkowany (~20-50% na dekodowaniu), bo
  najdrozszym krokiem jest CPU-owy `lut3d`, nie sam dekoding.
- **`pip install` zakazane.** Wszystko z `requirements.lock` juz jest w
  `.venv`. W szczegolnosci pakiet `opencv-contrib-python` dostarcza modul
  `cv2` (jest to zamierzone - "contrib" to nadzbior zwyklego
  `opencv-python`, `import cv2` dziala tak samo).
- **`-ss` przed `-i`.** Uzywane dla szybkiego seeka (input seeking). Dla
  okien pomiarowych rzedu kilkunastu-dwudziestu sekund to wystarczajaco
  dokladne dla metryk v0 (nie jest to montaz klatka-po-klatce).

## Metryki v0 - o czym trzeba pamietac

Progi klasyfikacji ruchu (`static`/`handheld`/`shaky`/`pan`) i flag
(`flagi_prowizoryczne`) sa PROWIZORYCZNE - zgrubne przyblizenia
literaturowe, nie skalibrowane na materiale Kuby. Zapisane w kazdym
raporcie w polu `progi_prowizoryczne`, do rewizji gdy bedzie material
porownawczy. `werdykty` jest zawsze `null` - ocene wpisuje czlowiek, nigdy
skrypt.
