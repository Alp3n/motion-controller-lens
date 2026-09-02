# Auto-Tune osi — instrukcja krok po kroku

Odpowiedź na otwarty punkt z `kanban.md`/`sterownik-sc4-hub.md`: „Auto-Tune
każdej osi pod obciążeniem — wymaga Windows z ClearView". Źródło:
`zbyszek/Clearpath-SC User Manual.pdf` (rev. 1.45), strony cytowane wprost
przy każdym ustaleniu.

**Uczciwe zastrzeżenie na start:** instrukcja Teknica **celowo nie opisuje**
ekranów kreatora Auto-Tune krok po kroku. Strona 67 manuala mówi wprost:

> *„Select this menu item to begin an Auto-Tuning session. The software is
> designed to walk you through the Auto-Tune process in a safe,
> step-by-step manner."*

Czyli: to **kreator w samym ClearView**, prowadzi użytkownika ekran po
ekranie na żywo — nie da się tego opisać dokładniej bez faktycznego
odpalenia kreatora. Ta instrukcja daje Ci wszystko, co jest **potwierdzone
w manualu** (warunki wstępne, ostrzeżenia, co zrobić z wynikiem) plus
kontekst specyficzny dla naszej maszyny — nie zmyśla nieistniejących
ekranów.

## 0. Dlaczego to w ogóle trzeba zrobić

> *„ClearPath-SC motors ship out pre-configured for unloaded use only.
> You must run the Auto-Tune application whenever you connect your motor
> to a different mechanical system."* (str. 19)

> *„Auto-Tune Fully Loaded. Auto-Tune with your motor connected to the
> mechanics exactly as it will run during normal operation. The default
> motor tuning file that comes with your motor is designed for no-load
> operation."* (str. 6)

Innymi słowy: **domyślne strojenie fabryczne zakłada silnik bez niczego na
wale.** Nasze osie mają śrubę, prowadnicę, masę zespołu ruchomego — bez
Auto-Tune serwo pracuje z parametrami dobranymi dla zupełnie innej
mechaniki. To nie jest kosmetyka — to podstawa poprawnej pracy regulatora.

## 1. Warunki wstępne (potwierdzone w manualu)

Zanim zaczniesz — ostrzeżenia dosłownie ze strony 10, obowiązujące zawsze
przy pracy z systemem pod napięciem, nie tylko przy Auto-Tune:

- Silniki muszą być pewnie przykręcone do stabilnej powierzchni.
- Żadnych luźnych elementów (kable, włosy, ubranie) w pobliżu wałów
  silników.
- **Zamontuj osłonę (finger-safe guard) wokół wału silnika**, jeśli jeszcze
  jej nie ma — Auto-Tune rusza silnikiem agresywnie, żeby wyznaczyć
  granice mechaniki.
- Nie „hot-swapuj" złączy zasilania DC (nie podłączaj/odłączaj przy
  włączonym zasilaniu magistrali DC) — to niszczy styki.

Dodatkowo, z ostrzeżenia na str. 67 wprost:

> *„Important: Avoid personal injuries, crashes and machine damage.
> Carefully read and follow all instructions presented during the
> Auto-Tune process."*

**Zasilanie musi dawać radę.** Strona 29: słaby zasilacz DC potrafi
„przysiąść" poniżej ok. 21,5 VDC pod obciążeniem szczytowym, co przerywa
komunikację i wywołuje zatrzymanie ochronne **w trakcie** Auto-Tune —
jeśli tuning nie kończy się do końca, to jeden z pierwszych podejrzanych.

## 2. Specyfika naszej instalacji — zanim odpalisz ClearView

Nasz SC4-Hub jest na stałe podłączony przez USB do **tego** mini PC
(Linux), na którym chodzi `motion-controller-bridge.service`. ClearView
działa tylko na Windows i wymaga **wyłącznego** dostępu do portu — dokładnie
tak, jak nasz mostek nie da uruchomić się drugi raz na tym samym porcie
(`docs/sterownik-sc4-hub.md`).

1. **Zatrzymaj mostek na Linuksie**, zanim podłączysz Windows:
   ```bash
   sudo systemctl stop motion-controller-bridge.service
   ```
   (Jeśli tego nie zrobisz, ClearView na Windows i tak nie połączy się z
   hubem — port będzie zajęty przez proces na Linuksie.)
2. **Fizycznie przełącz kabel USB** z SC4-Hub z tego mini PC na komputer z
   Windows, na którym masz zainstalowany ClearView (instalacja: strona 10
   manuala, `https://www.teknic.com/downloads/`).
3. Po zakończeniu tuningu (rozdział 4 niżej) — **przełącz kabel USB z
   powrotem** na ten mini PC i uruchom mostek ponownie:
   ```bash
   sudo systemctl start motion-controller-bridge.service
   ```
   Maszyna po tym będzie wymagać ponownego bazowania.

**Rób to po kolei, jedna oś na raz** — mapowanie osi po numerze seryjnym
jest w `bridge/machine.env` (X: S/N 90406231, Y: S/N 90406002, Z: S/N
90404362) — zanotuj, którego silnika dotyczy plik `.mtr`, żeby potem
wczytać go na właściwą oś.

## 3. Uruchomienie kreatora w ClearView

Ustalone wprost z manuala (str. 64, 67):

1. Połącz się z silnikiem w ClearView (motor musi być widoczny na liście
   silników — jeśli nie, sprawdź Preferences → Auto-Detect Ports, str. 62).
2. Menu **Setup → Auto-Tune**.
3. Kreator prowadzi dalej sam, na żywo, ekran po ekranie — to jest ten
   moment, w którym instrukcja Teknica świadomie kończy się i przechodzi
   w interaktywny dialog w programie. Czytaj każdy ekran uważnie przed
   kliknięciem dalej (to samo ostrzeżenie co w punkcie 1).

**Czego można się ogólnie spodziewać** (na podstawie tego, jak działają
kreatory tego typu w ClearView — **to już nie jest cytat z manuala**, tylko
ogólna wiedza o tej klasie narzędzia, potraktuj jako orientację, nie
scenariusz):
- Prośba o potwierdzenie, że mechanika jest bezpiecznie zamocowana i wolna
  droga ruchu w obu kierunkach.
- Silnik wykona serię ruchów testowych o rosnącej amplitudzie/prędkości,
  żeby zmierzyć bezwładność, tarcie i sztywność mechaniki.
- Po zakończeniu — podsumowanie wyniku (sukces/ostrzeżenia) i możliwość
  dostrojenia ręcznego (**Fine Tuning**, str. 67 — suwak „quieter" ↔
  „increased dynamic stiffness").

Jeśli kreator zgłasza błąd albo nie kończy się do końca — pierwsze
podejrzenie to zasilanie (punkt 1) albo mechanika blokująca pełny zakres
ruchu, nie błąd samego oprogramowania.

## 4. Po zakończeniu — zapis i co dalej

1. **File → Save Configuration (Ctrl+S)** w ClearView zapisuje ustawienia
   jako plik `.mtr` (str. 61) — zapisz z nazwą jednoznacznie wskazującą oś
   (np. `os-X-90406231.mtr`).
2. Zrób to dla każdej osi osobno, zanim przełączysz kabel z powrotem na
   Linux (punkt 2.3).
3. **Wczytanie `.mtr` z powrotem na Linuksie nie jest dziś zautomatyzowane
   w naszym projekcie** — to osobny, wciąż otwarty punkt w `kanban.md`.
   Mechanizm SDK do tego istnieje i jest potwierdzony:
   `sFnd::INode::Motion` ma odpowiednik `LoadingConfigFile.cpp` z paczki
   przykładów (`docs/przyklady-sdk-teknica.md` §7) — wczytanie pliku `.mtr`
   z poziomu C++/Linux. Zanim to zaimplementujemy w mostku, plik `.mtr`
   przechowaj (np. w `vendor/teknic/` albo osobno) — będzie potrzebny.

## Źródła

- `zbyszek/Clearpath-SC User Manual.pdf`, rev. 1.45: str. 6, 10, 19, 23,
  29, 61, 62, 64, 67 (cytaty jak oznaczono wyżej).
- `docs/przyklady-sdk-teknica.md` §7 — mechanizm wczytywania `.mtr` z
  Linuksa.
- `bridge/machine.env` — mapowanie osi po numerach seryjnych.
