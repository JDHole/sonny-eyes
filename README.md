# sonny-eyes

Pomiar percepcyjny ujec wideo (raport ujecia v0). Bierze plik kamery,
mierzy go ffmpegiem + numpy/OpenCV/scikit-image/colour-science na krotkim
oknie, zapisuje JSON z liczbami plus miniaturki i skopy PNG. Zero AI, zero
werdyktow - tylko liczby do dalszej analizy (przez Sonny'ego albo recznie).

Wersja v0: metryki tonalne/kolorystyczne/ostrosci/szumu na pojedynczym oknie
klipu. Ruch (v0.2, patrz nizej) jest wyjatkiem - liczony z calego klipu, nie
z okna. Brak wykrywania ciec (`montaz.segmenty` jest puste - miejsce na
przyszlosc).

## Jak odpalic

```
.venv/Scripts/python.exe scripts/measure.py --project "Nazwa Projektu" --files sciezka1.mov sciezka2.mp4
```

Opcje: `--cache-root X`, `--vault X` (nadpisuja config.toml), `--no-gpu`
(wymusza dekodowanie CPU), `--force` (przelicza nawet gdy raport juz
istnieje), `--window-start 5 --window-len 20` (domyslne okno dla klipow
>=30s; krotsze klipy mierzone sa w calosci od 0). Okno dotyczy metryk
tonalnosc/kolor/ostrosc/szum - ruch ma wlasny, niezalezny zakres (patrz
"Metryka ruchu v0.2" nizej).

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

Progi klasyfikacji ruchu i flag (`flagi_prowizoryczne`) sa PROWIZORYCZNE.
Zapisane w kazdym raporcie w polu `progi_prowizoryczne`, do rewizji gdy
bedzie wiecej materialu porownawczego. `werdykty` jest zawsze `null` - ocene
wpisuje czlowiek, nigdy skrypt.

## Metryka ruchu v0.2

v0.1 liczyla `cv2.phaseCorrelate` calych klatek z pierwszych 5 s OKNA
pomiarowego - mierzyla wiec czesto odkladanie/podnoszenie kamery na
poczatku ujecia (albo losowy fragment), a ruchome tlo (liscie, ludzie)
zawyzalo jitter, bo phase correlation nie odroznia ruchu kamery od ruchu
w kadrze. v0.2 liczy inaczej:

**Probkowanie (`plan_probkowania_ruchu` w `eyes/metrics.py`).** Caly klip
od 0 s (nie okno A): 10 kl/s dla klipow do 60 s, 5 kl/s powyzej, twardy
limit 180 s materialu - dluzszy klip jest obciety do pierwszych 180 s i
`ruch.obcieto_s` = 180.0 (inaczej `null`). Szerokosc 480 px, skala szarosci,
BEZ LUT (pomiar geometrii na luminancji nie potrzebuje korekcji
kolorystycznej), dekodowanie przez `eyes/decode.py` (GPU z fallbackiem na
CPU, jak reszta metryk).

**Ruch kamery oddzielony od ruchu obiektow.** Miedzy kazda para kolejnych
probek: `cv2.goodFeaturesToTrack` (maxCorners 400, qualityLevel 0.01,
minDistance 8) szuka cech na PIERWSZEJ klatce pary, `cv2.calcOpticalFlowPyrLK`
sledzi je na DRUGIEJ, `cv2.estimateAffinePartial2D` (RANSAC,
ransacReprojThreshold 3.0) dopasowuje transformacje podobienstwa (przesuniecie
+ rotacja + skala) do sledzonych punktow - punkty na ruchomych obiektach
(liscie na wietrze, przechodzien) sa zwykle outlierami wzgledem wspolnego
ruchu tla i RANSAC je odrzuca, zostawiajac ruch samej kamery. Z macierzy
brane sa dx, dy (przesuniecie w px) - rotacja i skala sa tez wyliczane, ale
v0.2 ich jeszcze nie wykorzystuje w klasyfikacji (zostawione pod przyszle
wykrywanie rolki/zoomu). Para jest odrzucana (`null`, liczy sie do
`ruch.pary_niepewne`) gdy sledzonych punktow jest mniej niz 12 (przed RANSAC)
albo udzial inlierow RANSAC wychodzi ponizej 30%.

**Profil co sekunde (`ruch.profil`).** Dla kazdej sekundy klipu:
`ruch_pct` (srednia |moving-average 0,5 s| przesuniecia, przeliczona na %
szerokosci kadru na sekunde - to jest "ruch zamierzony") i `jitter_pct`
(RMS odchylen surowego przesuniecia od tej samej ruchomej sredniej, tez w %
szerokosci) plus `conf` (srednia z udzialu inlierow RANSAC par w tej
sekundzie, 0..1 - orientacyjna pewnosc pomiaru tej sekundy, nie wchodzi do
klasyfikacji). Sekunda bez ANI JEDNEJ pewnej pary (np. niebo bez zadnej
faktury) dostaje `ruch_pct`/`jitter_pct` = `null`.

**Odcinki i "srodek" (`ruch.odcinki`, `ruch.srodek`).** Sekunda jest
"stabilna" gdy `jitter_pct` < S i `ruch_pct` < R (sekunda bez danych liczy
sie jako niestabilna). Sasiednie sekundy tego samego typu sa scalane w
odcinki `{"od_s","do_s","typ": "stabilny"|"ruch"}`. `ruch.srodek` to
najdluzszy odcinek stabilny (`{"od_s","do_s"}`) albo `null` gdy zaden nie
wyszedl stabilny.

**Agregaty i klasa licza sie z "srodka" w innym sensie niz `ruch.srodek`
powyzej** - tu "srodek" to caly klip MINUS pierwsze i ostatnie 2 sekundy
(zakres staly, nie wykryty odcinek; klip krotszy niz 6 s liczy sie z
calosci). Z tego zakresu: `ruch.jitter_rms_pct` (RMS jittera) i
`ruch.ruch_zamierzony_pct_s` (srednia ruchu, ta sama nazwa pola co w v0.1,
inna metoda liczenia). Do bramkowania klasy "postawiona" i `ruch.brzegi`
uzywane sa MEDIANY tego samego zakresu (`ruch.mediana_jitter_srodka_pct` i
`ruch.mediana_ruch_srodka_pct`, oba pola dodane ponad literalna specyfikacje
zadania) zamiast sredniej/RMS - mediana jest odporna, gdy prawdziwe
odkladanie/podnoszenie kamery trwa troche dluzej niz 2 s trymu i
zanieczyszcza jedna sekunde na krawedzi zakresu; srednia/RMS w tym miejscu
potrafila falszywie zablokowac klase "postawiona" (zlapane na danych
syntetycznych przed uruchomieniem na prawdziwych klipach). `ruch.brzegi.
poczatek_ruch`/`koniec_ruch` = pierwsze/ostatnie 2 sekundy sa OBIE
POTWIERDZONE niestabilne (poza progiem stabilnosci I z wystarczajaca
pewnoscia pomiaru `conf` >= 0.30 - patrz "czego nie lapie" nizej, punkt 4)
ORAZ "srodek" (mediana) jest stabilny. Dodatkowo z CALEGO klipu (bez
trymu): `ruch.mediana_jitter_pct`, `ruch.p90_jitter_pct`.

**Klasa (`ruch.klasa`, lista).** Pierwsza pasujaca z wykluczajacych sie
warunkow (potem niezaleznie dopisywany "pan"):
- `postawiona` - "srodek" (mediana) stabilny I ktorykolwiek brzeg w ruchu.
- `static` - CALY klip (bez trymu, MEDIANA jittera i ruchu) stabilny.
- `handheld` - `jitter_rms_pct` (srodek) < granica (0.6).
- `shaky` - `jitter_rms_pct` (srodek) >= granica.
- `pan` (dodatkowo) - `ruch_zamierzony_pct_s` (srodek) > R.

Flaga `trzesie` w `flagi_prowizoryczne` odpala sie WYLACZNIE gdy klasa
zawiera `shaky` (jitter srodka, nie brzegow).

**Progi prowizoryczne** (pole `progi_prowizoryczne` w kazdym raporcie,
`eyes/metrics.py:PROGI_PROWIZORYCZNE`): `jitter_stabilny_max` (S) = 0.4,
`ruch_stabilny_max` (R) = 3.0, `jitter_shaky_min` = 0.6. Skalibrowane
recznie na 3 klipach werdyktowych Kuby z 2026-09-05 (DSCF1414 - kamera
polozona na murku miedzy dwoma niestabilnymi brzegami; DSCF3066 - hero
Anagi, bardziej shaky niz 1414; DSCF2988 - statyw), NIE na pelnej,
zroznicowanej probce - do rewizji gdy bedzie wiecej materialu. S i R
zaczynaly od 0.15/1.0 (zgrubne przyblizenie literaturowe); na DSCF1414
(czlowiek balansujacy w kadrze podczas skadinad "stabilnego" ujecia
polozonej kamery) tyle wystarczylo, zeby co kilka-kilkanascie sekund
przebic prog i fragmentowac jeden dlugi stabilny odcinek na kilkanascie
krotkich - podniesione do wartosci, przy ktorych realny szum tej sceny
(jitter ~0.02-0.15, sporadyczne doskoki do ~0.3-0.36; ruch ~0.3-2.6%/s)
miesci sie w "stabilne", a prawdziwa niestabilnosc na poczatku klipu
(jitter do ~6, ruch do ~55%/s) zostaje "ruch" z duzym zapasem.

**Czego ta metoda NIE lapie.** (1) Rotacja/skala z macierzy afinicznej sa
liczone, ale nieuzywane - rolka kamery albo zoom podczas ujecia nie maja
dzis wplywu na klase. (2) "Pan" jest liczony ze sredniej |moving-average|
przesuniecia, nie z uredniowanego WEKTORA - bardzo silny, chaotyczny jitter
(nie prawdziwy kierunkowy ruch) moze w skrajnym przypadku tez przekroczyc
prog R i dopisac "pan" (zaobserwowane na syntetycznym tescie skrajnym, nie
na prawdziwych klipach kalibracyjnych). (3) Sceny o niskiej fakturze (czyste
niebo, wypalona sciana) daja za malo cech dla `goodFeaturesToTrack` - pary
albo cale sekundy koncza jako niepewne/`null`, nie jako fikcyjne zero.
(4) `ruch.brzegi` patrzy sztywno na pierwsze/ostatnie 2 sekundy - odkladanie
kamery trwajace wyraznie dluzej moze czesciowo "wyciec" poza to okno (choc
mediana srodka lagodzi zanieczyszczenie na styku, patrz wyzej). (5) Rozpad
trackingu (np. reka zaslaniajaca obiektyw przy starcie/stopie nagrania,
albo ktokolwiek/cokolwiek bardzo blisko obiektywu) moze dac pojedyncza
sekunde z fizycznie bezsensownym `ruch_pct` (setki % szerokosci kadru) przy
niskim `conf` - `zakres_niestabilny` (uzywane przez `ruch.brzegi`) wymaga
`conf` >= 0.30 zeby taka sekunda MOGLA potwierdzic niestabilnosc brzegu,
ale `ruch.profil` sam w sobie takie wartosci nadal pokazuje bez filtrowania
(zlapane na ostatniej sekundzie DSCF2988 - statyw, prawdopodobnie dotkniecie
kamery przy zatrzymaniu nagrania). (6) Osoba/obiekt zajmujacy duza czesc
kadru i poruszajacy sie w sposob spojny (np. sylwetka balansujaca pod
wiatr) moze czesciowo "przeciekac" do `ruch_pct`, nawet gdy RANSAC
poprawnie odrzuca wiekszosc jego punktow jako outlierow - stad podniesienie
progu R (patrz "progi prowizoryczne" wyzej) zamiast zakladania idealnej
separacji kamera/obiekt. (7) Dekodowanie calego klipu (do 180 s) zamiast
pierwszych 5 s wydluza czas pomiaru na dlugich klipach ZNACZACO, mimo
optymalizacji `scale_cuda` w `eyes/decode.py` (GPU skaluje klatke PRZED
`fps`, nie po - realny zysk ~30-45% na dekodowaniu, bo `hwdownload`
przenosi juz male klatki zamiast pelnej rozdzielczosci zrodla). Przyczyna:
dekodowanie 4K 10-bit HEVC tej kamery (nawet z `-hwaccel cuda`) dziala w
praktyce w okolicach 200-300 kl/s efektywnego throughput NIEZALEZNIE od
docelowego fps probkowania (5 albo 10) - `fps` w filtergraphie odrzuca
klatki PO zdekodowaniu, nie PRZED, wiec caly zakres czasowy i tak jest w
pelni dekodowany. Dla klipow > ~60-90 s to realnie wiecej niz +8 s wobec
v0.1 - patrz `pomiar.czas_calkowity_s` w raporcie i sesja z 2026-09-05 w
historii repo po konkretne liczby.
