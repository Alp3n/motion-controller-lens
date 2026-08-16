# Konfiguracja osi maszyny

Ustalenia dotyczące tego, jak opisujemy osie: długość, punkt bazowania, limity
i przełożenie posuwu. Ekran `/axes` i plik konfiguracji są realizacją tego
modelu — zmiany w kodzie opisuje
[`zmiany/ekran-konfiguracji-osi.md`](zmiany/ekran-konfiguracji-osi.md).

## Model osi

Każda oś (X, Y, Z) ma pięć parametrów:

| Parametr | Znaczenie |
|---|---|
| długość fizyczna [mm] | całkowity skok mechaniczny osi |
| punkt bazowania | gdzie po bazowaniu leży **zero** osi: `minus`, `plus`, `srodek` |
| limit programowy MIN/MAX [mm] | zakres, w którym maszyna ma się poruszać |
| przełożenie [mm/obrót] | ile milimetrów przejeżdża oś na jeden obrót silnika |

**Zakresu fizycznego nie podaje się wprost — wynika z długości i punktu
bazowania.** Dla osi o długości 300 mm:

```
minus   0 ────────────────────── 300      zero na końcu „minusowym"
plus  -300 ────────────────────── 0       zero na końcu „plusowym"
srodek -150 ───────── 0 ───────── 150     zero w środku osi
```

Limity programowe muszą się mieścić w zakresie fizycznym (mogą go dotykać).
Taki zapis pilnuje spójności: nie da się ustawić limitów, których oś nie
osiągnie, i nie da się zapomnieć o relacji między zerem a mechaniką.

### Dlaczego tak, a nie „min/max osobno"

Zakres wpisywany wprost pozwalał zapisać stany bez sensu (zakres szerszy niż
oś) i milczał o tym, gdzie leży zero — a to zero jest punktem, do którego
wraca bazowanie. Długość + punkt bazowania to dwie wielkości, które monter
zna wprost z maszyny.

## Co wynika z czego

- **Limity programowe** = obszar roboczy przy walidacji programów `.prg`
  (`validate_work_area`) **oraz** granica ruchu ręcznego (JOG). Program
  z punktem poza limitem nie zostanie wczytany; JOG poza limit jest odrzucany
  z komunikatem, bez alarmu.
- **Przełożenie** przelicza milimetry na obroty serwa w mostku
  (`imp/mm = imp/obr ÷ mm/obr`). Rozdzielczość `imp/obr` mostek **czyta
  z serwa**; z konfiguracji bierze wyłącznie `mm/obr`.
- **Punkt bazowania** określa układ współrzędnych — nie uruchamia procedury
  bazowania. Samo bazowanie (czujniki, kierunek najazdu) konfiguruje się
  w serwie przez ClearView; do czasu tej konfiguracji mostek robi zerowanie
  programowe, co bazowaniem **nie jest** (patrz
  [`sterownik-sc4-hub.md`](sterownik-sc4-hub.md)).

## Gdzie mieszka konfiguracja

Plik JSON wskazany zmienną `AXES_CONFIG` (domyślnie `config/axes.json`;
`start.sh`/`start.bat` ustawiają `../config/axes.json`). Serwer jest jedynym
właścicielem tego pliku i rozsyła jego treść dalej:

```
ekran /axes ──PUT /api/axes──► serwer ──AXCFG──► mostek SC4-Hub ──► serwa
                                 │
                                 └─► walidacja programów, JOG
```

Dopóki pliku nie ma, konfiguracja powstaje z dawnych zmiennych `WORK_*`, więc
maszyna zachowuje się jak przed wprowadzeniem ekranu. **Uszkodzony plik
zatrzymuje start serwera** — praca na cicho podstawionych limitach byłaby
gorsza niż brak startu.

## Komenda AXCFG (protokół mostka)

```
AXCFG <X|Y|Z> MMREV=<mm/obr> [SOFTMIN=<mm> SOFTMAX=<mm>] [LEN=<mm>] [HOME=<minus|plus|srodek>]
```

- serwer wysyła ją po **każdym** nawiązaniu połączenia i po każdej zmianie
  konfiguracji — mostek trzyma te dane tylko w pamięci,
- działa także w stanie `ALARM` (inaczej po alarmie nie dałoby się dosłać
  konfiguracji i każda komenda kończyłaby się błędem),
- `SOFTMIN`/`SOFTMAX` podaje się razem; bez nich mostek pracuje **bez limitów**
  — tak, żeby mostek uruchomiony bez serwera nie odrzucał wszystkich ruchów.

## Ograniczenia — świadome

- Ekran **nie jest funkcją bezpieczeństwa**. Limity programowe to warstwa
  wygody i ochrony przed pomyłką w programie; krańcówki, E-stop i odcięcie
  zasilania mocy realizuje niezależny układ sprzętowy.
- Limity nie chronią przed złym przełożeniem: przy błędnym `mm/obr` oś jedzie
  o inny dystans, niż wynika z zadanej pozycji, i limit liczony w milimetrach
  też jest wtedy przesunięty. Po każdej zmianie przełożenia **trzeba
  zweryfikować skok przejazdem kontrolnym** na wolnym posuwie.
- Przełożenie jest jedną liczbą (mm na obrót silnika). Przekładnię pasową lub
  reduktor uwzględnia się w tej liczbie (`skok śruby ÷ przełożenie`), bo poza
  tym przelicznikiem nic w systemie nie potrzebuje ich osobno.
- Maszyna w ruchu (`RUNNING`, `HOMING`) odrzuca zapis konfiguracji — trwający
  cykl został zaplanowany pod poprzednie limity.
