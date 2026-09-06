# Screeny do dorobienia

Lista obrazków, na które README (PL i EN) ma już wstawione placeholdery z
komentarzem `<!-- TODO screenshot -->`. Nazwy plików są takie same w obu
wersjach językowych - nie zmieniaj ich bez poprawienia obu README.

Wspólne zasady:

- PNG, szerokość 1200-1600 px (README skaluje do szerokości kolumny).
- Poniżej 500 KB na plik, jeśli się da - inaczej narzędzia AI czytające repo
  rekompresują je do JPEG.
- Bez prywatnych ścieżek na widoku: kadruj tak, żeby nie było widać
  `C:/Users/jdziu/...` ani nazw katalogów z vaulta. Jeśli ścieżka musi być
  widoczna, zmierz demo w katalogu o neutralnej nazwie (`eyes-out/demo`).
- Ten plik (`docs/img/README.md`) jest tylko briefem dla autora. Można go
  skasować, gdy wszystkie obrazki będą na miejscu.

---

> Stan 2026-09-06: obrazki 1-4 wygenerowane automatycznie z wyników klipu DSCF0934 (Canarian Tweety EP03); `raport-json.png` przycięty do pierwszych 1500 px. Obrazek 5 (`bez-pomiaru-vs-z-pomiarem.png`) czeka na autora.

## 1. `przeglad.png`

**Gdzie:** README, sekcja 1 (nagłówek, pierwszy z trzech obrazków).
Alt PL: "Strona przeglądu: cegły, liczby, flagi".
Alt EN: "Review page: bricks, numbers, flags".

**Co ma być na obrazku:** strona wygenerowana przez `python -m eyes review`,
zescrollowana tak, żeby widać było 4-6 kafelków klipów naraz plus pasek
kontrolek (sortowanie, filtry flag) nad nimi. Na kafelkach mają być widoczne:
cegła (najostrzejsza klatka), blok liczb (czerń p5, środek p50, światła p99,
przepał, ostrość, nasycenie), linia ruchu z klasą i drganiem, oraz co najmniej
jeden kafelek z zapaloną flagą (`trzesie` albo `czern_zabita`), żeby widać było
kolorowy chip.

**Jak zrobić:** zrzut okna przeglądarki z otwartym `_przeglad.html`, bez paska
zakładek i bez adresu (albo z adresem `file:///.../eyes-out/demo/_przeglad.html`).

---

## 2. `przebieg.png`

**Gdzie:** README, sekcja 1 (drugi z trzech obrazków). Warto tym samym plikiem
zilustrować sekcję "Przebieg ujęcia" w Szybkim starcie, jeśli uznasz, że jeden
raz to za mało.
Alt PL: "Wykres przebiegu ujęcia".
Alt EN: "Clip profile chart".

**Co ma być na obrazku:** czysty PNG `{id}_przebieg.png` prosto z
`eyes-out/<projekt>/<id>/scopes/`, bez ramki okna. Trzy panele: jasność po LUT
(p5 / p50 / p99), drganie, ruch zamierzony.

**Wybór klipu jest ważny:** weź klip, na którym wykres coś opowiada - najlepiej
klasa `postawiona` albo długie ujęcie z wyraźnym odcinkiem stabilnym i
niestabilnymi brzegami, żeby na panelach było widać zaznaczony odcinek stabilny
i przekroczenia progów. Klip w całości `shaky` daje trzy płaskie szumy i nic z
tego nie wynika.

---

## 3. `raport-json.png`

**Gdzie:** README, sekcja 1 (trzeci z trzech obrazków).
Alt PL: "Raport JSON jednego klipu".
Alt EN: "JSON report for one clip".

**Co ma być na obrazku:** fragment prawdziwego pliku `{id}.json` otwartego w
edytorze z kolorowaniem składni i zwiniętymi długimi tablicami (`tonalnosc.profil`,
`ruch.profil`, `ruch.odcinki`). Ma być widać `wersja_metryk`, `zrodlo`,
`tonalnosc`, `ruch.klasa`, `flagi_prowizoryczne`, `werdykty: null` i
`niepewnosc` - czyli te miejsca, o których mówi tekst README (jawny `null`,
jawna niepewność, brak werdyktu).

**Uwaga:** zwiń albo przytnij tablice, żeby na jednym ekranie zmieściły się
zarówno metryki, jak i `werdykty: null` u dołu. To jest cały sens tego screena.

---

## 4. `skopy.png`

**Gdzie:** README, sekcja "Wynik", pod opisem strony przeglądu.
Alt PL: "Waveform i vectorscope jednego klipu".
Alt EN: "Waveform and vectorscope for one clip".

**Co ma być na obrazku:** waveform i vectorscope TEGO SAMEGO klipu, zestawione
obok siebie (montaż dwóch PNG z `scopes/` w jeden plik, waveform po lewej,
vectorscope po prawej, wspólne tło). Pod spodem albo w rogu warto wpisać id
klipu i timestamp klatki, z której skopy zostały wyrenderowane - to jest
`skopy[].t_s` w raporcie.

**Wybór klipu:** materiał z wyraźnym charakterem, np. zachód słońca (waveform
z czernią nisko i słońcem pod sufitem, vectorscope z jawnym wychyleniem w
stronę żółci i pomarańczy). Neutralna szara scena nie pokaże niczego.

---

## 5. `bez-pomiaru-vs-z-pomiarem.png`

**Gdzie:** README, koniec sekcji "Problem: jak AI ogląda film".
Alt PL: "Co widzi model bez pomiaru vs z pomiarem".
Alt EN: "What the model sees without measurement vs with it".

**Co ma być na obrazku:** jedna grafika porównawcza, dwie kolumny, ten sam klip.

- Lewa kolumna, "bez pomiaru": klatka z klipu i pod nią zdania, jakie model
  jest w stanie o niej powiedzieć samym patrzeniem - kategorie, nie wartości
  ("ciepła scena", "chyba ostre", "chyba z ręki"). Warto pokazać ograniczenie
  wejścia: klatka zmniejszona do 2576 px na dłuższym boku, opcjonalnie z
  nałożoną siatką patchy albo podpisem "92 x 52 = 4784 patche, zero metadanych".
- Prawa kolumna, "z pomiarem": ta sama klatka i pod nią liczby z raportu,
  napisane wprost: `p5`, `p99`, `clip_hi_pct`, `sat_mean`, `cct_est_k`,
  `ruch.klasa`, `jitter_rms_pct`. Najlepiej dokładnie te wartości, które siedzą
  w prawdziwym raporcie tego klipu.

**Uwaga:** to jedyny obrazek z tej listy, którego nie da się wygenerować
narzędziem - trzeba go złożyć ręcznie (Figma, Resolve, cokolwiek). To
jednocześnie najważniejszy obrazek w całym README, bo jednym spojrzeniem tłumaczy
tezę: nie chodzi o to, że model widzi gorzej, tylko że widzi INNĄ kategorię
informacji.

**Kontrola:** liczby na prawej kolumnie muszą się zgadzać z prawdziwym raportem.
Wymyślone wartości w obrazku, który dowodzi tezy "mierz, nie zgaduj", to
najgorszy możliwy błąd w tym repo.
