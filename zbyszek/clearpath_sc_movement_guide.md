# Kompendium: Ruch Podatny i Uczenie Trajektorii na Serwosilnikach Teknic ClearPath-SC

Niniejsze opracowanie podsumowuje architekturę sprzętową, algorytmy oraz wytyczne bezpieczeństwa niezbędne do implementacji trybu uczenia przez prowadzenie ręczne (ruch podatny / antygrawitacja) dla wieloosiowego ramienia robotycznego (cobota) bazującego na serwomechanizmach **Teknic ClearPath-SC**.

---

## 1. Architektura Sprzętowa i Komunikacja

### Konfiguracja Sprzętowa (Skalowalność do 16 Osi)
Do obsługi pełnego systemu wykorzystuje się **cztery huby SC4-USB**, z których każdy zarządza maksymalnie 4 osiami (łącznie 16 osi). 
* **Niezależne Kanały Hardware:** Każdy hub SC4-USB tworzy dedykowany, niezależny port szeregowy/COM w komputerze PC. Komunikacja między hubami odbywa się w pełni równolegle na poziomie sprzętowym.
* **Optymalizacja Topologii:** Główne stawy robota przenoszące największe obciążenia (baza, ramię, przedramię) należy podłączyć do **osobnych hubów SC4-USB**. Mniejsze osie (nadgarstek, chwytak) mogą współdzielić kanały szeregowe, ponieważ wymagają mniejszej częstotliwości próbkowania.

### Częstotliwość Odpytywania (Polling Rate)
* **Pojedyncza Oś na Hubie:** Stabilne odpytywanie w pętli **200 – 250 Hz** (co 4 – 5 ms).
* **Trzy Osie na Jednym Hubie (Zestaw Startowy):** Zalecana częstotliwość pętli wynosi **100 Hz** (odczyt i korekta co 10 ms). Czas odpytywania trzech silników sekwencyjnie zajmuje ok. 3–4 ms, co pozostawia bezpieczny margines dla systemu operacyjnego. Czas reakcji 10 ms jest całkowicie niezauważalny dla ludzkiej ręki.

---

## 2. Struktura Danych Trajektorii

Do precyzyjnego nagrywania i odtwarzania ścieżki w bibliotece **sFoundation SDK** stosuje się dwupoziomową strukturę opartą na stemplach czasowych, co pozwala zachować dynamikę i zmienną prędkość ruchu operatora.

```cpp
// 1. Ramka stanu robota w danej milisekundzie
struct JointState {
    uint32_t timestampMs;       // Czas od rozpoczęcia nagrywania
    std::vector<int32_t> positions; // Pozycje enkoderów dla wszystkich osi
};

// 2. Kolekcja przechowująca całą nagraną ścieżkę w RAM
std::vector<JointState> recordedTrajectory;
```

---

## 3. Algorytm Aktywnej Asysty Prądowej (Wspomaganie Momentowe)

W trybie pozycjonowania (PID) silnik dąży do zniwelowania błędu pozycji (`Tracking Error`). Wdrożenie asysty polega na ciągłym modyfikowaniu pozycji docelowej w zależności od siły przykładanej przez operatora, dzięki czemu silnik "ucieka" przed naciskiem dłoni.

### Kod źródłowy pętli asysty (C++)
```cpp
#include "pubSysCls.h"
#include <vector>
#include <cmath>
#include <algorithm>

const int16_t TRQ_DEADBAND = 6;       // Martwa strefa (np. 6% momentu) ignorująca szumy i tarcie static
const double ASSIST_GAIN = 15.0;      // Współczynnik "lekkości" asysty (dobierany eksperymentalnie)
const int32_t MAX_STEP_PER_CYCLE = 60; // Bezpiecznik maksymalnej prędkości na cykl

// Uproszczona pętla dla 3 osi na jednym hubie SC4-USB
void RunTripleAxisAssist(std::vector<INode*>& motors, std::vector<JointState>& trajectory, bool& isTeaching) {
    // Odczyt wagi statycznej ramienia w celu kompensacji grawitacji (Static Torque Offset)
    int16_t gravityOffset0 = motors[0]->Status.TorqueMeasured.Value();
    int16_t gravityOffset1 = motors[1]->Status.TorqueMeasured.Value();
    int16_t gravityOffset2 = motors[2]->Status.TorqueMeasured.Value();

    int32_t targetPos0 = motors[0]->Status.PositionMeasured.Value();
    int32_t targetPos1 = motors[1]->Status.PositionMeasured.Value();
    int32_t targetPos2 = motors[2]->Status.PositionMeasured.Value();

    auto startTime = std::chrono::steady_clock::now();

    while (isTeaching) {
        auto currentTime = std::chrono::steady_clock::now();
        uint32_t elapsedMs = std::chrono::duration_cast<std::chrono::milliseconds>(currentTime - startTime).count();

        // OŚ 0
        int16_t netTorque0 = motors[0]->Status.TorqueMeasured.Value() - gravityOffset0;
        if (std::abs(netTorque0) > TRQ_DEADBAND) {
            int32_t delta0 = (netTorque0 > 0 ? 1 : -1) * (std::abs(netTorque0) - TRQ_DEADBAND) * ASSIST_GAIN;
            targetPos0 += std::clamp(delta0, -MAX_STEP_PER_CYCLE, MAX_STEP_PER_CYCLE);
            motors[0]->Motion.MoveToPosition(targetPos0, MoveArgs::MOVE_TARGET_ABSOLUTE);
        }

        // OŚ 1
        int16_t netTorque1 = motors[1]->Status.TorqueMeasured.Value() - gravityOffset1;
        if (std::abs(netTorque1) > TRQ_DEADBAND) {
            int32_t delta1 = (netTorque1 > 0 ? 1 : -1) * (std::abs(netTorque1) - TRQ_DEADBAND) * ASSIST_GAIN;
            targetPos1 += std::clamp(delta1, -MAX_STEP_PER_CYCLE, MAX_STEP_PER_CYCLE);
            motors[1]->Motion.MoveToPosition(targetPos1, MoveArgs::MOVE_TARGET_ABSOLUTE);
        }

        // OŚ 2
        int16_t netTorque2 = motors[2]->Status.TorqueMeasured.Value() - gravityOffset2;
        if (std::abs(netTorque2) > TRQ_DEADBAND) {
            int32_t delta2 = (netTorque2 > 0 ? 1 : -1) * (std::abs(netTorque2) - TRQ_DEADBAND) * ASSIST_GAIN;
            targetPos2 += std::clamp(delta2, -MAX_STEP_PER_CYCLE, MAX_STEP_PER_CYCLE);
            motors[2]->Motion.MoveToPosition(targetPos2, MoveArgs::MOVE_TARGET_ABSOLUTE);
        }

        // Zapis punktu do trajektorii
        JointState frame;
        frame.timestampMs = elapsedMs;
        frame.positions.push_back(motors[0]->Status.PositionMeasured.Value());
        frame.positions.push_back(motors[1]->Status.PositionMeasured.Value());
        frame.positions.push_back(motors[2]->Status.PositionMeasured.Value());
        trajectory.push_back(frame);

        std::this_thread::sleep_for(std::chrono::milliseconds(10)); // 100 Hz
    }
}
```

---

## 4. Algorytm Odtwarzania Trajektorii (Playback)

Odtwarzanie wymaga precyzyjnego respektowania interwałów czasowych `timestampMs`. Dzięki wewnętrznym filtrom wygładzającym profile ruchu (współczynnik RAS / Jerk limiting) w procesorach DSP silników ClearPath, odtwarzany ruch jest płynny pomimo ewentualnych drżeń ręki operatora.

```cpp
void PlaybackTrajectory(std::vector<INode*>& motors, const std::vector<JointState>& trajectory) {
    if (trajectory.empty()) return;

    // Przywrócenie 100% momentu obrotowego
    for (auto* motor : motors) {
        motor->Limits.TorqueLimit.Value(100);
        motor->EnableRequest(true);
    }

    // Bezpieczny dojazd do punktu startowego i czekanie na zakończenie ruchu
    const JointState& startPoint = trajectory.front();
    for (size_t i = 0; i < motors.size(); ++i) {
        motors[i]->Motion.MoveToPosition(startPoint.positions[i], MoveArgs::MOVE_TARGET_ABSOLUTE);
    }
    for (auto* motor : motors) {
        while (!motor->Status.IsReady()) { std::this_thread::sleep_for(std::chrono::milliseconds(10)); }
    }

    // Pętla odtwarzania
    auto playbackStartTime = std::chrono::steady_clock::now();
    size_t currentFrameIndex = 0;

    while (currentFrameIndex < trajectory.size()) {
        auto currentTime = std::chrono::steady_clock::now();
        uint32_t elapsedPlaybackMs = std::chrono::duration_cast<std::chrono::milliseconds>(currentTime - playbackStartTime).count();

        if (elapsedPlaybackMs >= trajectory[currentFrameIndex].timestampMs) {
            const JointState& frame = trajectory[currentFrameIndex];
            for (size_t i = 0; i < motors.size(); ++i) {
                motors[i]->Motion.MoveToPosition(frame.positions[i], MoveArgs::MOVE_TARGET_ABSOLUTE);
            }
            currentFrameIndex++;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1)); // Precyzyjne sprawdzanie warunku czasowego
    }
}
```

---

## 5. Przegląd Protokółów i Architektury Systemów Ruchu

Podczas skalowania projektu warto przeanalizować ograniczenia i korzyści płynące z migracji z architektury opartej na PC + Teknic SC na przemysłowe magistrale czasu rzeczywistego:

1. **Teknic ClearPath-SC (Obecny system):** Niski koszt, darmowe SDK (sFoundation). Ograniczeniem jest brak gwarancji czasu rzeczywistego w systemach Windows/Linux, co narzuca bezpieczny limit częstotliwości pętli na poziomie 100–250 Hz. Całkowicie wystarczający dla asysty dłoni.
2. **EtherNet/IP:** Najmniej efektywny w aplikacjach aktywnej asysty prądowej. Podatność na wahania opóźnień pakietów (jitter) w standardowych sieciach bez warstwy CIP Sync wywołuje skokowe reakcje silnika na dotyk, co prowadzi do drgań mechaniki.
3. **EtherCAT:** Standard przemysłowy w robotyce. Częstotliwość pracy rzędu 1000–4000 Hz realizowana sprzętowo zapewnia idealnie gładką "wirtualną nieważkość". Przejście na EtherCAT wymaga jednak wymiany silników na modele ze zintegrowanym kontrolerem EtherCAT oraz zakupu licencji środowiska czasu rzeczywistego (np. Beckhoff TwinCAT 3).

---

## 6. Propozycje Dalszego Rozwoju Algorytmu (Zagadnienia Zaawansowane)

Aby system działał z precyzją fabrycznego cobota, w kolejnych etapach prac programistycznych warto wdrożyć następujące moduły:

1. **Dynamiczny Model Grawitacyjny (Trygonometryczny):** Zastąpienie stałego `gravityOffset` funkcją matematyczną obliczającą moment grawitacyjny w czasie rzeczywistym na podstawie aktualnych kątów ramienia ($M_g = m \cdot g \cdot l \cdot \cos(lpha)$). Zapobiegnie to "uciekaniu" lub opadaniu osi podczas drastycznych zmian wyciągnięcia ramienia.
2. **Skalowanie i Edycja Trajektorii (Time-stretching):** Modyfikacja pętli odtwarzania pozwalająca na zmianę prędkości ruchu (np. wykonanie zapisanego zadania 2x szybciej) poprzez programowe mnożenie lub dzielenie wartości `timestampMs` podczas odczytu.
3. **Funkcja Wirtualnego Tłumienia (Damping):** Algorytm redukujący bezwładność ramienia. Polega na odejmowaniu ułamka aktualnej prędkości silnika od obliczonej pozycji docelowej (`targetPos -= VelocityMeasured * dampingFactor`). Chroni to maszynę przed niekontrolowanym "odfrunięciem" po mocniejszym pchnięciu przez operatora.
4. **Wirtualne Ściany (Geofencing / Safety Zones):** Programowe ograniczenie pozycji `targetPos` do bezpiecznego zakresu przestrzennego. Jeśli operator spróbuje pchnąć ramię w strefę zakazaną (np. w stronę ramy maszyny lub stanowiska człowieka), algorytm asysty zignoruje ten kierunek siły i zablokuje ruch.