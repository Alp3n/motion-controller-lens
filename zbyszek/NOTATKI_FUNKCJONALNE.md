# Notatki funkcjonalne — motion-controller-lens

Uporządkowane notatki robocze. Punkty już ustalone wcześniej (mechanizm
nadpisz/przywróć parametry przy podprogramie technologa, koncepcja 12NC,
Global Stop na SC4-HUB) nie są tu powtarzane — patrz `DECYZJE_2026-08-25.md`.

## 1. Bazowanie (homing)

- Bez wyłączników krańcowych — wykorzystać wbudowaną funkcję bazowania
  serwonapędu Teknic (dla modelu silnika z odpowiednim firmware/wersją).
- Przycisk „dojazd do HOME wszystkich osi" na środku klawiszy strzałek XY.
- Ekran konfiguracji bazowania — oddzielny od ekranu prędkości/siły,
  z możliwością zdefiniowania dowolnej liczby osi.

## 2. Prędkości i siły — konfiguracja trzypoziomowa

- **Siła globalna** — wartość domyślna 20%.
- **Siła dla ruchu podczas pracy maszyny** (cykl) — osobno dla każdego
  zdefiniowanego ruchu, domyślnie 15%.
- **Siła dla ruchu podczas wykonywania programu technologa** — domyślnie 10%.
- Prędkości maksymalne — konfigurowalne dla wszystkich osi.
- Prędkości robocze — osobno dla: ruchu roboczego, bazowania, trybu JOG.
- Siła i prędkość konfigurowalne **na każdym kroku programu**, zależnie od
  pozycji (np. oś X, pozycja 100, ACC, DCC, prędkość, siła 10%) — sprawdzić
  w bibliotece Teknic dostępne funkcje pod to zastosowanie.
- W programie technologa też powinna być możliwość ustawienia siły per
  operacja; jeśli nieustawiona — brana wartość domyślna z ekranu parametrów
  maszyny.
- Ekran konfiguracji prędkości/siły — oddzielny od ekranu bazowania osi.

## 3. Program maszyny i program technologa

- Ekran definiowania ruchów maszyny — analogiczny do edytora technologa,
  ale z możliwością wstawienia w dowolnym miejscu **skoku do wybranego
  podprogramu technologa** (traktowane jako rodzaj operacji).
- Musi też uwzględniać rozpędzanie, prędkość zadaną, hamowanie i siłę dla
  każdego zdefiniowanego ruchu.
- Ekran definiowania operacji — osobne okno/zakładka.

## 4. Wrzeciono

- Włączenie wrzeciona przy starcie maszyny — przełącznik na ekranie
  Start/Stop.
- Włączenie wrzeciona przy starcie programu — dwie opcje do zdefiniowania
  w konfiguracji maszyny.
- Sterowanie prędkością wrzeciona — port PWM.
- Włącz/wyłącz wrzeciona — osobny port cyfrowy I/O.
- Konfiguracja rozpędzania i hamowania wrzeciona dla sterowania PWM.

## 5. Drzwi / osłona (interlock)

- Dodatkowy port wejściowy czyta sygnał z portu wyjściowego (PWM ~100Hz
  albo prosty 0/1) — jeśli sygnał OK, maszyna może się uruchomić.
- Funkcja aktywna tylko w pracy automatycznej, z niezależnym
  włącz/wyłącz w ekranie konfiguracyjnym.

## 6. Tryby pracy

- **Manualny** — przytrzymanie przycisku wybranej osi = ruch, puszczenie
  = zatrzymanie.
- **Półautomatyczny** — jeden pełny cykl.
- **Automatyczny** — pętla nieskończona cyklu maszyny do odczytu E-Stop
  lub otwarcia drzwi; plus przyciski start/stop na ekranie.
- Ekran konfiguracji pracy osi uruchamiany po starcie jako pętla
  nieskończona, z wyborem trybu jak wyżej.

## 7. Ekrany — ogólnie

- Ekran główny: prosty, niezbędne przyciski i komunikaty, nazwa maszyny
  „Demontaż pinów z optyki", logo WALKNER.
- Ekran diagnostyczny (tylko admin): definiowanie, ustawianie, praca
  ręczna, praca półautomatyczna z funkcjami zabezpieczeń, praca
  automatyczna z funkcjami zabezpieczeń.

## 8. Zarządzanie programami

- Kopiowanie programów technologicznych przez opcję „zapisz jako".

## 9. Uprawnienia i logowanie

| Ekran                        | Role z dostępem            | Domyślny PIN |
| ----------------------------- | --------------------------- | ------------ |
| Konfiguracja osi maszyny      | admin                       | 123321       |
| Edytor technologa              | admin, technolog             | 456          |
| Panel operatora                | admin, technolog, operator   | 789          |

- Logowanie: operator → panel operatora; technolog → edytor; admin →
  całość programu.

## 10. Inspiracje / referencje

- Sterownik MD488 jako punkt odniesienia funkcjonalnego (ma dużo funkcji,
  ale brak konfiguracji siły — Twoje serwa Teknic mają to natywnie).
- Ekrany mają wyglądać inaczej niż MD488 — bardziej rozbite na
  funkcjonalności.
- Warto przejrzeć inne kontrolery (web/GitHub) pod kątem inspiracji
  funkcjonalnej.

---

## Sugestie i pytania (do dopracowania)

1. **PIN-y 123321 / 456 / 789 to bardzo słabe kody** — dla ekranu, który
   odblokowuje konfigurację siły i prędkości ruchu (czyli realnie wpływa na
   bezpieczeństwo), warto rozważyć dłuższe/losowe kody i osobne konta
   zamiast wspólnego PIN-u na rolę — inaczej trudno rozliczyć, kto faktycznie
   zmienił parametry.

2. **Bazowanie bez wyłączników krańcowych** — sama funkcja bazowania serwa
   (np. przez wykrycie oporu/prądu silnika przy dojeździe do mechanicznego
   ogranicznika) działa dobrze do ustalenia punktu zerowego, ale zwykle nie
   zastępuje fizycznych krańcówek jako niezależnego zabezpieczenia przed
   wyjechaniem poza zakres przy awarii enkodera/utracie pozycji. Warto
   sprawdzić w dokumentacji Teknic, czy dla Twojego modelu funkcja bazowania
   ma wbudowaną detekcję przeciążenia/oporu (żeby nie zgniatała mechaniki
   przy każdym bazowaniu), i rozważyć **programowe limity krańcowe** jako
   dodatkową warstwę, nawet bez fizycznych czujników.

3. **Sygnał drzwi przez PWM ~100Hz odczytywany programowo — to nie jest
   sygnał bezpieczeństwa w sensie certyfikowanym.** To dobry pomysł jako
   dodatkowa logika interlocku (np. wykrycie przeciętego przewodu przez brak
   sygnału), ale nie powinien zastępować sprzętowego Global Stop na SC4-HUB
   — powinien go uzupełniać. Innymi słowy: otwarcie drzwi powinno docelowo
   fizycznie przerywać zasilanie/zezwolenie przez niezależny obwód
   bezpieczeństwa (kurtyna/wyłącznik drzwiowy → Global Stop), a odczyt PWM
   w softcie służy tylko do diagnostyki i logiki trybu automatycznego, nie
   do samego zatrzymania.

4. **Odpowiedź na pytanie „Funkcje zabezpieczeń maszyny — opisz":**
   Typowy zestaw dla maszyny tego typu (obróbka wiertarsko-frezarska,
   serwa z kontrolą siły):
   - **E-stop sprzętowy** — niezależny obwód, odcina moc silnikom
     bezpośrednio (nie przez oprogramowanie).
   - **Global Stop na SC4-HUB** — zatrzymuje wszystkie osie w łańcuchu,
     podłączony do tego samego obwodu bezpieczeństwa co E-stop.
   - **Osłony/kurtyny z interlockiem** — fizycznie uniemożliwiają dostęp do
     strefy roboczej podczas pracy automatycznej; otwarcie przerywa
     zezwolenie na ruch przez obwód bezpieczeństwa, nie tylko przez
     odczyt w aplikacji.
   - **Ograniczenie siły/momentu** — przy Twoich serwach z kontrolą siły to
     naturalna dodatkowa warstwa: niski limit siły w trybie ręcznym/JOG i
     przy bazowaniu ogranicza skutki kolizji czy przytrzaśnięcia.
   - **Funkcja "martwego człowieka" w trybie ręcznym** — ruch tylko przy
     przytrzymanym przycisku (już to zaplanowałeś w trybie manualnym).
   - **Programowe limity ruchu** — w obrębie fizycznych granic osi, jako
     dodatkowa warstwa niezależna od bazowania.
   - **Blokada trybu automatycznego przy braku zezwolenia/otwartych
     drzwiach** — już zaplanowane.
   - **Rozdzielenie uprawnień** — zmiana parametrów siły/prędkości/programu
     maszyny wymaga wyższych uprawnień niż start/stop produkcji.

   Ważne zastrzeżenie: to jest ogólny, inżynierski przegląd typowych funkcji,
   nie formalna ocena ryzyka. Skoro maszyna trafia na produkcję w fabryce w
   UE, **przed uruchomieniem produkcyjnym warto to przejść z osobą
   uprawnioną do oceny ryzyka maszyn (dyrektywa maszynowa, oznakowanie CE)**
   — szczególnie sam obwód E-stop/kurtyn i jego kategoria bezpieczeństwa
   (np. wg PN-EN ISO 13849-1) nie powinny być projektowane wyłącznie na
   podstawie tych notatek.
