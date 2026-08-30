# Propozycja: ruchy head-tail i asymetryczne (temat C)

Ostatni nieblokowany punkt z tematu C w planie rozwoju:
„Rozważyć ruchy head-tail dla zagłębiania w Z... i asymetryczne (inne
przyspieszenie niż hamowanie)". W przeciwieństwie do reszty tego, co
zrobiłem samodzielnie w tej sesji, **tego świadomie nie zaimplementowałem
bez Ciebie** — to zmiana zachowania fizycznego ruchu narzędzia w materiale,
a nie ekran czy zapis danych. Złe założenie tutaj może się objawić jako
gorsza jakość cięcia albo złamane narzędzie, nie jako czytelny błąd
w interfejsie. To poniżej jest **propozycja do przeczytania i decyzji**,
nie gotowy kod.

## 1. Head-tail (zagłębianie w Z)

**Dziś:** każde zagłębienie w Z to jeden ruch z jednym posuwem — od
pozycji bezpiecznej do głębokości przejścia, tym samym `POSUW` co reszta
operacji.

**Pomysł:** rozbić zagłębienie na dwa odcinki: szybki dojazd przez
powietrze/luźny materiał, potem wolniejszy, precyzyjny odcinek tuż przed
zadaną głębokością (mniejsze ryzyko wyszczerbienia przy wejściu, cichszy
i dokładniejszy start cięcia).

**Do ustalenia, zanim to zakoduję:**

- **Skąd bierze się granica** między „szybko" a „wolno"? Trzy warianty:
  - stała **odległość** od zadanego Z (np. „zwolnij 2 mm przed głębokością") —
    prosta, ale niewłaściwa dla płytkich i bardzo głębokich zagłębień naraz,
  - **procent** głębokości operacji — skaluje się z operacją, ale trudniej
    przewidzieć w mm,
  - osobne pole w operacji/programie, wpisywane ręcznie przez technologa
    (jak dziś `PRZEJSCIA`/`PRZYROST`) — najbardziej elastyczne, ale kolejna
    kolumna w już gęstej tabeli edytora.
- **Czy to nowe pole w `.prg` (format 5), czy globalny parametr maszyny**
  (jedna wartość dla wszystkich operacji, ekran `/profiles` albo `/axes`)?
  Kolumna per operacja pasuje do tego, jak już działa `MOMENT`/`POSUW` —
  ale to złożoność, którą technolog musi rozumieć przy każdym programie.
- **Druga prędkość** — osobna wartość, czy ułamek `POSUW` operacji
  (np. „tail" = 30% posuwu)?

**Moja rekomendacja**, jeśli mam wybrać jedną opcję: parametr globalny na
`/profiles` (mm od głębokości + mnożnik prędkości), a nie pole per operacja —
mniej do wypełniania w codziennej pracy, spójne z tym, jak już działa
`vel_jog`/`vel_home` per oś. Ale to Twoja maszyna i Twój materiał — jeśli
różne operacje realnie potrzebują różnych ustawień, pole per operacja
będzie właściwsze mimo dodatkowej kolumny.

## 2. Ruchy asymetryczne (inne przyspieszenie niż hamowanie)

**Dziś:** symulator w ogóle nie liczy przyspieszenia/hamowania — każdy ruch
to liniowa interpolacja pozycji ze stałą prędkością (`_move_to` w
`machine.py`). Pola `accel`/`decel` w profilach parametrów (etap 2 tematu B)
**są zapisywane, ale nic ich nie czyta** — to czysta zaszłość po pierwszym
projekcie modelu, nie coś, co kiedyś działało i się zepsuło.

**Co by to znaczyło zrobić naprawdę:** doliczenie realnego rozpędzania/
hamowania (profil trapezowy prędkości) do `_move_to`. To dotyka **każdego**
ruchu symulatora — JOG, bazowania, programu, cyklu — i **czasu trwania
każdego ruchu w testach**, które dziś zakładają w przybliżeniu stały czas
= dystans / posuw. Nie jest to zmiana, którą warto zrobić bez możliwości
szybkiej korekty, gdyby coś w mierzeniu czasu w istniejących testach
subtelnie się rozjechało.

**Pytanie do Ciebie, zanim to zacznę:** czy w ogóle chcesz, żeby symulator
odzwierciedlał przyspieszenie/hamowanie? To wpływa tylko na to, jak
realistycznie wygląda i „czuje się" praca w symulatorze — **realnemu
sterownikowi asymetrii i tak nie da się dziś wysłać** (protokół mostka
nie ma komendy rozpędzania/hamowania, tylko docelowy posuw), więc efekt
byłby wyłącznie kosmetyczny/testowy, dopóki protokół mostka nie zostanie
rozszerzony (temat C/H, C++ i sprzęt) — realna asymetria ruchu i tak
ustawia się dziś w servach przez ClearView.

## Co proponuję

Jeśli się zgadzasz z moją rekomendacją w części 1 (parametr globalny na
`/profiles`), mogę to zaimplementować od razu przy kolejnej sesji —
wystarczy jedno zdanie potwierdzenia. Część 2 (asymetria w symulatorze)
zostawiłbym jako **osobną decyzję** — to praca kosmetyczna o realnym
ryzyku dla testów, a nie coś, czego dziś brakuje do produkcji.
