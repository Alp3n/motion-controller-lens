// Firmware sterownika Teknic ClearCore — maszyna do ocinania wlewków.
//
// Rola: wykonywanie komend ruchu przysyłanych przez serwer maszyny po TCP
// (port 8500, protokół tekstowy — jedna komenda na linię) oraz odczyt
// JEDNEGO sygnału zezwolenia z niezależnego systemu bezpieczeństwa na
// dedykowanym wejściu cyfrowym. Bez zezwolenia żaden ruch się nie wykona,
// a trwający ruch jest natychmiast przerywany.
//
// Protokół (odpowiedź zawsze jedną linią: "OK ..." albo "ERR <opis>"):
//   PING                      -> OK PONG
//   STATUS                    -> OK STATE=<stan> EN=<0/1> X=<mm> Y=<mm> Z=<mm> SP=<0/1>
//   HOME                      -> bazowanie wszystkich osi
//   MOVEXY <x> <y> <posuw>    -> ruch interpolowany XY [mm, mm/min]
//   MOVEZ <z> <posuw>         -> ruch osi Z [mm, mm/min]
//   JOG <os> <dyst> <posuw>   -> ruch ręczny o zadany dystans
//   SPINDLE <0/1> [obr/min]   -> wrzeciono wył/zał
//   STOP                      -> natychmiastowe zatrzymanie (stan ALARM)
//   RESET                     -> kasowanie alarmu (stan NOT_HOMED)
//
// Budowanie: projekt biblioteki ClearCore (Microchip Studio / CMake),
// patrz README.md w tym katalogu.

#include "ClearCore.h"
#include "EthernetTcpServer.h"

// ---------------------------------------------------------------------------
// Konfiguracja sprzętowa
// ---------------------------------------------------------------------------

// Osie na złączach silnikowych M0..M2, wrzeciono załączane przekaźnikiem z IO-0.
// Serwa ClearPath skonfigurowane w MSP w trybie zgodnym z generowaniem kroków
// przez ClearCore (patrz README — tryb pracy musi się zgadzać po obu stronach).
#define MOTOR_X ConnectorM0
#define MOTOR_Y ConnectorM1
#define MOTOR_Z ConnectorM2
#define SPINDLE_RELAY ConnectorIO0

// Dedykowane wejście sygnału zezwolenia z niezależnego systemu bezpieczeństwa.
// Poziom wysoki = zezwolenie aktywne. Układ bezpieczeństwa dodatkowo odcina
// zasilanie mocy serw niezależnie od tego sygnału.
#define SAFETY_ENABLE_INPUT ConnectorDI6

// Przeliczniki mechaniki: kroki na milimetr dla każdej osi
// (przełożenie śruby/paska x rozdzielczość wejściowa serwa ustawiona w MSP).
constexpr double STEPS_PER_MM_X = 800.0;
constexpr double STEPS_PER_MM_Y = 800.0;
constexpr double STEPS_PER_MM_Z = 1600.0;

constexpr uint32_t TCP_PORT = 8500;
constexpr uint32_t ACCEL_STEPS_S2 = 100000; // przyspieszenie [kroki/s^2]

// ---------------------------------------------------------------------------
// Stan maszyny
// ---------------------------------------------------------------------------

enum class State { INIT, NOT_HOMED, HOMING, READY, RUNNING, ALARM };

static State state = State::INIT;
static bool spindleOn = false;
// pozycja zadana w krokach (pozycję rzeczywistą raportują enkodery serw ClearPath)
static double posX = 0, posY = 0, posZ = 0; // [mm]

static EthernetTcpServer server(TCP_PORT);
static EthernetTcpClient client;

static const char *StateName(State s) {
    switch (s) {
        case State::INIT: return "INIT";
        case State::NOT_HOMED: return "NOT_HOMED";
        case State::HOMING: return "HOMING";
        case State::READY: return "READY";
        case State::RUNNING: return "RUNNING";
        case State::ALARM: return "ALARM";
    }
    return "?";
}

// ---------------------------------------------------------------------------
// Bezpieczeństwo
// ---------------------------------------------------------------------------

static bool SafetyEnabled() {
    return SAFETY_ENABLE_INPUT.State();
}

// Natychmiastowe zatrzymanie wszystkich osi i wrzeciona.
static void EmergencyStop(const char *reason) {
    MOTOR_X.MoveStopAbrupt();
    MOTOR_Y.MoveStopAbrupt();
    MOTOR_Z.MoveStopAbrupt();
    SPINDLE_RELAY.State(false);
    spindleOn = false;
    state = State::ALARM;
    (void)reason;
}

// Wywoływane w każdej iteracji pętli głównej ORAZ w pętlach oczekiwania na
// koniec ruchu — utrata zezwolenia przerywa ruch w czasie < 1 ms + rampa stop.
static void CheckSafety() {
    if (!SafetyEnabled() &&
        (state == State::RUNNING || state == State::HOMING)) {
        EmergencyStop("utrata sygnalu zezwolenia");
    }
}

// ---------------------------------------------------------------------------
// Ruchy
// ---------------------------------------------------------------------------

static bool MotorsMoving() {
    return !MOTOR_X.StepsComplete() || !MOTOR_Y.StepsComplete() ||
           !MOTOR_Z.StepsComplete();
}

// Blokujące oczekiwanie na koniec ruchu z ciągłą kontrolą zezwolenia.
static bool WaitForMoveDone() {
    while (MotorsMoving()) {
        CheckSafety();
        if (state == State::ALARM) {
            return false;
        }
    }
    return true;
}

static void SetFeedRate(MotorDriver &motor, double stepsPerMm, double feedMmMin) {
    uint32_t stepsPerSec = (uint32_t)(feedMmMin / 60.0 * stepsPerMm);
    motor.VelMax(stepsPerSec > 0 ? stepsPerSec : 1);
    motor.AccelMax(ACCEL_STEPS_S2);
}

// Interpolowany ruch XY: prędkości osi skalowane proporcjonalnie do składowych
// dystansu, żeby obie osie kończyły ruch jednocześnie (interpolacja liniowa).
static bool MoveXY(double x, double y, double feedMmMin) {
    if (!SafetyEnabled()) return false;
    double dx = x - posX, dy = y - posY;
    double dist = sqrt(dx * dx + dy * dy);
    if (dist < 1e-6) return true;

    SetFeedRate(MOTOR_X, STEPS_PER_MM_X, feedMmMin * fabs(dx) / dist);
    SetFeedRate(MOTOR_Y, STEPS_PER_MM_Y, feedMmMin * fabs(dy) / dist);
    MOTOR_X.Move((int32_t)(dx * STEPS_PER_MM_X));
    MOTOR_Y.Move((int32_t)(dy * STEPS_PER_MM_Y));
    if (!WaitForMoveDone()) return false;
    posX = x;
    posY = y;
    return true;
}

static bool MoveZ(double z, double feedMmMin) {
    if (!SafetyEnabled()) return false;
    double dz = z - posZ;
    if (fabs(dz) < 1e-6) return true;
    SetFeedRate(MOTOR_Z, STEPS_PER_MM_Z, feedMmMin);
    MOTOR_Z.Move((int32_t)(dz * STEPS_PER_MM_Z));
    if (!WaitForMoveDone()) return false;
    posZ = z;
    return true;
}

// Bazowanie: serwa ClearPath wykonują homing samodzielnie (funkcja homingu
// skonfigurowana w MSP); tu inicjujemy je po kolei i zerujemy pozycje.
static bool HomeAll() {
    state = State::HOMING;
    MotorDriver *motors[] = {&MOTOR_Z, &MOTOR_X, &MOTOR_Y}; // najpierw Z w górę
    for (MotorDriver *m : motors) {
        m->EnableRequest(true);
        while (m->HlfbState() != MotorDriver::HLFB_ASSERTED) {
            CheckSafety();
            if (state == State::ALARM) return false;
        }
    }
    posX = posY = posZ = 0;
    state = State::READY;
    return true;
}

// ---------------------------------------------------------------------------
// Protokół TCP
// ---------------------------------------------------------------------------

static void Reply(const char *text) {
    client.Send(text);
    client.Send("\n");
}

static void HandleCommand(char *line) {
    char cmd[16] = {0};
    double a = 0, b = 0, c = 0;
    char axis = 0;

    if (sscanf(line, "%15s", cmd) != 1) {
        Reply("ERR pusta komenda");
        return;
    }

    if (strcmp(cmd, "PING") == 0) {
        Reply("OK PONG");
    } else if (strcmp(cmd, "STATUS") == 0) {
        char buf[128];
        snprintf(buf, sizeof(buf),
                 "OK STATE=%s EN=%d X=%.3f Y=%.3f Z=%.3f SP=%d",
                 StateName(state), SafetyEnabled() ? 1 : 0, posX, posY, posZ,
                 spindleOn ? 1 : 0);
        Reply(buf);
    } else if (strcmp(cmd, "STOP") == 0) {
        EmergencyStop("STOP z serwera");
        Reply("OK");
    } else if (strcmp(cmd, "RESET") == 0) {
        if (state == State::ALARM || state == State::INIT) {
            state = State::NOT_HOMED;
        }
        Reply("OK");
    } else if (!SafetyEnabled()) {
        // wszystkie pozostałe komendy wymagają aktywnego zezwolenia
        Reply("ERR brak sygnalu zezwolenia - ruch zablokowany");
    } else if (strcmp(cmd, "HOME") == 0) {
        Reply(HomeAll() ? "OK" : "ERR bazowanie przerwane");
    } else if (strcmp(cmd, "MOVEXY") == 0) {
        if (sscanf(line, "%*s %lf %lf %lf", &a, &b, &c) != 3) {
            Reply("ERR MOVEXY <x> <y> <posuw>");
        } else if (state != State::READY && state != State::RUNNING) {
            Reply("ERR maszyna nie jest gotowa (wymagane bazowanie)");
        } else {
            state = State::RUNNING;
            bool ok = MoveXY(a, b, c);
            if (state != State::ALARM) state = State::READY;
            Reply(ok ? "OK" : "ERR ruch przerwany");
        }
    } else if (strcmp(cmd, "MOVEZ") == 0) {
        if (sscanf(line, "%*s %lf %lf", &a, &b) != 2) {
            Reply("ERR MOVEZ <z> <posuw>");
        } else if (state != State::READY && state != State::RUNNING) {
            Reply("ERR maszyna nie jest gotowa (wymagane bazowanie)");
        } else {
            state = State::RUNNING;
            bool ok = MoveZ(a, b);
            if (state != State::ALARM) state = State::READY;
            Reply(ok ? "OK" : "ERR ruch przerwany");
        }
    } else if (strcmp(cmd, "JOG") == 0) {
        if (sscanf(line, "%*s %c %lf %lf", &axis, &a, &b) != 3) {
            Reply("ERR JOG <X/Y/Z> <dystans> <posuw>");
        } else {
            bool ok = false;
            switch (axis) {
                case 'X': ok = MoveXY(posX + a, posY, b); break;
                case 'Y': ok = MoveXY(posX, posY + a, b); break;
                case 'Z': ok = MoveZ(posZ + a, b); break;
                default: Reply("ERR nieznana os"); return;
            }
            Reply(ok ? "OK" : "ERR ruch przerwany");
        }
    } else if (strcmp(cmd, "SPINDLE") == 0) {
        int on = 0;
        sscanf(line, "%*s %d", &on);
        SPINDLE_RELAY.State(on != 0);
        spindleOn = (on != 0);
        Reply("OK");
    } else {
        Reply("ERR nieznana komenda");
    }
}

// ---------------------------------------------------------------------------
// Pętla główna
// ---------------------------------------------------------------------------

int main() {
    // wejście zezwolenia i wyjście wrzeciona
    SAFETY_ENABLE_INPUT.Mode(Connector::INPUT_DIGITAL);
    SPINDLE_RELAY.Mode(Connector::OUTPUT_DIGITAL);
    SPINDLE_RELAY.State(false);

    // tryb generowania kroków dla złącz silnikowych
    MotorMgr.MotorInputClocking(MotorManager::CLOCK_RATE_NORMAL);
    MotorMgr.MotorModeSet(MotorManager::MOTOR_ALL,
                          Connector::CPM_MODE_STEP_AND_DIR);

    // sieć: adres z DHCP (docelowo stały adres w konfiguracji instalacji)
    EthernetMgr.Setup();
    EthernetMgr.DhcpBegin();
    server.Begin();

    state = State::NOT_HOMED;

    char lineBuf[128];
    size_t lineLen = 0;

    while (true) {
        CheckSafety();

        if (!client.Connected()) {
            client = server.Accept();
            lineLen = 0;
            continue;
        }

        while (client.BytesAvailable() > 0) {
            int ch = client.Read();
            if (ch < 0) break;
            if (ch == '\n' || lineLen >= sizeof(lineBuf) - 1) {
                lineBuf[lineLen] = '\0';
                if (lineLen > 0) {
                    HandleCommand(lineBuf);
                }
                lineLen = 0;
            } else if (ch != '\r') {
                lineBuf[lineLen++] = (char)ch;
            }
        }
    }
}
