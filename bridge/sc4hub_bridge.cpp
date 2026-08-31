/*
 * Mostek SC4-Hub — zastępuje firmware ClearCore.
 *
 * Wystawia na TCP ten sam protokół tekstowy, co firmware/clearcore/, ale
 * zamiast sterownika ClearCore używa biblioteki Teknic sFoundation i serw
 * ClearPath-SC podłączonych przez SC4-Hub po USB. Dzięki temu serwer maszyny
 * (server/) działa bez zmian — wystarczy MACHINE_MODE=clearcore
 * i CLEARCORE_HOST=127.0.0.1.
 *
 * UWAGA — BEZPIECZEŃSTWO
 * Mostek NIE realizuje funkcji bezpieczeństwa. Odpowiada za nie niezależny,
 * certyfikowany układ odcinający sprzętowo zasilanie mocy serw. Mostek jedynie
 * czyta wejście Global Stop huba i odrzuca komendy ruchu, gdy zezwolenia brak.
 *
 * Budowanie:  make
 * Uruchomienie:  ./sc4hub_bridge
 * Mapowanie osi: ./sc4hub_bridge --identify
 */

#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cctype>
#include <cstring>
#include <string>
#include <vector>

#include "pubSysCls.h"

using namespace sFnd;

// --- konfiguracja (zmienne środowiskowe) ----------------------------------

static std::string envStr(const char *name, const char *fallback) {
    const char *v = getenv(name);
    return v && *v ? std::string(v) : std::string(fallback);
}
static double envNum(const char *name, double fallback) {
    const char *v = getenv(name);
    return v && *v ? atof(v) : fallback;
}

struct Config {
    std::string bind = envStr("BRIDGE_BIND", "127.0.0.1");
    int port = (int)envNum("BRIDGE_PORT", 8500);

    // Przelicznik jednostek: serwo nie wie nic o milimetrach.
    // countsPerRev jest ODCZYTYWANE z serwa przy otwarciu portu
    // (Info.PositioningResolution); COUNTS_PER_REV służy tylko do nadpisania.
    double countsPerRev = envNum("COUNTS_PER_REV", 0);
    // wartość startowa przełożenia dla każdej osi; właściwe wartości przysyła
    // serwer komendą AXCFG (ekran „Konfiguracja osi")
    double mmPerRev = envNum("MM_PER_REV", 5.0);

    double maxRpm = envNum("MAX_RPM", 800);
    double accRpmPerSec = envNum("ACC_RPM_PER_SEC", 2000);

    // wyjście wrzeciona: "none" | "brake0" | "brake1"
    std::string spindleOutput = envStr("SPINDLE_OUTPUT", "none");
} cfg;

/* Konfiguracja pojedynczej osi — przysyłana przez serwer komendą AXCFG.
   Dopóki nie przyjdzie, mostek pracuje z przełożeniem z MM_PER_REV i BEZ
   limitów programowych: mostek uruchomiony samodzielnie (bez serwera) nie może
   odrzucać wszystkich ruchów, ale też nie udaje, że czegoś pilnuje. */
struct AxisCfg {
    double mmPerRev = 0;         // mm na obrót silnika
    double softMin = 0;          // limit programowy dolny [mm]
    double softMax = 0;          // limit programowy górny [mm]
    bool limits = false;         // czy limity są znane
    double length = 0;           // długość fizyczna osi [mm] — do wydruku
    std::string home = "?";      // punkt bazowania: minus | plus | srodek
};
static AxisCfg axCfg[3];

/* Odrzucenie komendy, które NIE jest awarią maszyny — np. ruch poza limit
   programowy. Alarm w takiej sytuacji zmuszałby operatora do RESET-u po
   każdym dojechaniu do granicy zakresu. */
struct Reject {
    std::string msg;
};

// --- stan mostka -----------------------------------------------------------

enum class State { INIT, NOT_HOMED, HOMING, READY, RUNNING, ALARM };

static const char *stateName(State s) {
    switch (s) {
    case State::INIT: return "INIT";
    case State::NOT_HOMED: return "NOT_HOMED";
    case State::HOMING: return "HOMING";
    case State::READY: return "READY";
    case State::RUNNING: return "RUNNING";
    case State::ALARM: return "ALARM";
    }
    return "ALARM";
}

struct Axis {
    const char *name;
    size_t nodeIndex;
};

static SysManager *mgr = nullptr;
static IPort *port = nullptr;
static Axis axes[3] = {{"X", 0}, {"Y", 1}, {"Z", 2}};
static State state = State::INIT;
static bool axisEnabled[3] = {false, false, false};
// Oś zluzowana: moment zdjęty celowo, żeby dało się nią ruszyć ręcznie.
// Komendy ruchu takiej osi są odrzucane aż do ponownego zaciśnięcia (HOLD).
static bool axisReleased[3] = {false, false, false};
static bool spindleOn = false;
/* Stan obu wyjść huba (BRAKE_0, BRAKE_1). Płytka nie pozwala ich odczytać,
   więc trzymamy to, co sami ustawiliśmy — i dlatego zerujemy je przy starcie
   (patrz resetOutputs), zamiast zgadywać, w jakim stanie zostały. */
static bool outputState[2] = {false, false};
static std::string alarmMsg;

// Ustawiane, gdy STOP przyszedł w trakcie ruchu — wtedy odpowiedź na komendę
// ruchu jest pomijana (klient, który ją wysłał, i tak został anulowany).
static bool moveAbortedByStop = false;

// --- pomocnicze ------------------------------------------------------------

static INode &nodeOf(int axisIdx) { return port->Nodes(axes[axisIdx].nodeIndex); }

static double countsPerMm(int axisIdx) {
    return cfg.countsPerRev / axCfg[axisIdx].mmPerRev;
}

static double posMm(int axisIdx) {
    return nodeOf(axisIdx).Motion.PosnMeasured.Value() / countsPerMm(axisIdx);
}

/* Limit programowy osi. Sprawdzany dla każdego celu ruchu — także dla ruchów
   zleconych przez program, choć te są walidowane już w serwerze. */
static void checkSoftLimit(int axisIdx, double targetMm) {
    const AxisCfg &c = axCfg[axisIdx];
    if (!c.limits) return;
    if (targetMm < c.softMin - 1e-4 || targetMm > c.softMax + 1e-4) {
        char buf[192];
        snprintf(buf, sizeof(buf),
                 "oś %s: pozycja %.3f mm poza limitem programowym (%.3f..%.3f mm)",
                 axes[axisIdx].name, targetMm, c.softMin, c.softMax);
        throw Reject{buf};
    }
}

/* Zezwolenie z układu bezpieczeństwa, czytane z wejścia Global Stop huba.
   Semantyka wg przykładu SC4-IO: true = wejście NIE jest zaasertowane. */
static bool safetyEnabled() {
    if (!port) return false;
    return port->GrpShutdown.GetGlobalStopInputState();
}

static void setAlarm(const std::string &msg) {
    alarmMsg = msg;
    state = State::ALARM;
    spindleOn = false;
}

// --- sterowanie węzłami ----------------------------------------------------

/* Załącza moment na wskazanych osiach. Oś zluzowana nie jest załączana po
   cichu — to byłoby zaskoczeniem dla operatora, który zluzował ją celowo. */
static void enableAxes(const std::vector<int> &which) {
    for (int a : which)
        if (axisReleased[a])
            throw std::string("oś ") + axes[a].name +
                  " jest zluzowana — zaciśnij ją (HOLD) przed ruchem";

    std::vector<int> toWait;
    for (int a : which) {
        if (axisEnabled[a]) continue;
        INode &n = nodeOf(a);
        n.Status.AlertsClear();
        n.Motion.NodeStopClear();
        n.EnableReq(true);
        toWait.push_back(a);
    }
    double timeout = mgr->TimeStampMsec() + 3000;
    for (int a : toWait) {
        while (!nodeOf(a).Motion.IsReady()) {
            if (mgr->TimeStampMsec() > timeout)
                throw std::string("oś ") + axes[a].name + " nie zgłosiła gotowości";
        }
        axisEnabled[a] = true;
    }
}

static void disableAxis(int a) {
    if (!port) return;
    nodeOf(a).EnableReq(false);
    axisEnabled[a] = false;
}

static void disableNodes() {
    if (!port) return;
    for (int a = 0; a < 3; a++) disableAxis(a);
}

/* Zluzowanie / zaciśnięcie osi. Zluzowana oś nie stawia oporu i można nią
   ruszyć ręcznie — na maszynie z mechaniką oś pionowa opadnie pod własnym
   ciężarem, jeśli nie ma hamulca. */
static void setReleased(const std::vector<int> &which, bool released) {
    if (state == State::RUNNING || state == State::HOMING)
        throw std::string("nie można luzować osi w trakcie ruchu maszyny");
    for (int a : which) {
        if (released) {
            disableAxis(a);
            axisReleased[a] = true;
        } else {
            axisReleased[a] = false;
        }
    }
    if (!released) enableAxes(which);
}

static void applyLimits(INode &n, double rpm) {
    if (rpm < 1) rpm = 1;
    if (rpm > cfg.maxRpm) rpm = cfg.maxRpm;
    n.AccUnit(INode::RPM_PER_SEC);
    n.VelUnit(INode::RPM);
    n.Motion.AccLimit = cfg.accRpmPerSec;
    n.Motion.VelLimit = rpm;
}

static void stopAll(const char *why) {
    if (!port) return;
    for (size_t i = 0; i < port->NodeCount(); i++)
        port->Nodes(i).Motion.NodeStop(STOP_TYPE_ABRUPT);
    setAlarm(why);
}

// deklaracja: obsługa komend przychodzących w trakcie ruchu
static bool pollDuringMove(int fd, std::string &pending);

/* Czeka na zakończenie ruchu zadanych osi.
   W trakcie czekania nasłuchuje gniazda, żeby STOP działał natychmiast,
   i pilnuje sygnału zezwolenia. */
static void waitMoves(const std::vector<int> &axisIdx, double timeoutMs, int fd,
                      std::string &pending) {
    double deadline = mgr->TimeStampMsec() + timeoutMs;
    for (;;) {
        bool allDone = true;
        for (int a : axisIdx)
            if (!nodeOf(a).Motion.MoveIsDone()) allDone = false;
        if (allDone) return;

        if (!safetyEnabled()) {
            stopAll("utrata sygnału zezwolenia — zatrzymanie awaryjne");
            throw std::string("utrata sygnału zezwolenia");
        }
        if (pollDuringMove(fd, pending)) {
            stopAll("zatrzymano przyciskiem STOP");
            moveAbortedByStop = true;
            throw std::string("ruch przerwany");
        }
        if (mgr->TimeStampMsec() > deadline) {
            stopAll("przekroczono czas ruchu");
            throw std::string("przekroczono czas ruchu");
        }
    }
}

// --- ruch ------------------------------------------------------------------

static void moveAxisAbs(int axisIdx, double targetMm, double feedMmMin, int fd,
                        std::string &pending) {
    INode &n = nodeOf(axisIdx);
    checkSoftLimit(axisIdx, targetMm);
    double deltaMm = targetMm - posMm(axisIdx);
    if (std::fabs(deltaMm) < 1e-4) return;

    applyLimits(n, feedMmMin / axCfg[axisIdx].mmPerRev);
    int32_t target = (int32_t)llround(targetMm * countsPerMm(axisIdx));
    n.Motion.MoveWentDone();
    n.Motion.MovePosnStart(target, /*targetIsAbsolute=*/true);

    double est = n.Motion.MovePosnDurationMsec(target, true) * 1.5 + 3000;
    waitMoves({axisIdx}, est, fd, pending);
}

/* Ruch XY. Prędkości osi są dobrane tak, żeby obie skończyły w tym samym
   czasie — to przybliżenie interpolacji liniowej. Rampy przyspieszenia
   powodują odchyłkę od prostej na początku i końcu ruchu; przy operacjach
   LINIA trzeba to zweryfikować pomiarowo. Patrz docs/sterownik-sc4-hub.md. */
static void moveXY(double xMm, double yMm, double feedMmMin, int fd, std::string &pending) {
    checkSoftLimit(0, xMm);
    checkSoftLimit(1, yMm);
    double dx = xMm - posMm(0), dy = yMm - posMm(1);
    double dist = std::hypot(dx, dy);
    if (dist < 1e-4) return;

    double tMin = dist / feedMmMin;           // czas przejazdu [min]
    double vx = std::fabs(dx) / tMin;         // [mm/min]
    double vy = std::fabs(dy) / tMin;

    // wspólne skalowanie, jeśli któraś oś przekracza limit obrotów
    double rpmX = vx / axCfg[0].mmPerRev, rpmY = vy / axCfg[1].mmPerRev;
    double over = std::fmax(rpmX / cfg.maxRpm, rpmY / cfg.maxRpm);
    if (over > 1.0) { rpmX /= over; rpmY /= over; }

    INode &nx = nodeOf(0);
    INode &ny = nodeOf(1);
    std::vector<int> moving;
    double estMs = 0;

    if (std::fabs(dx) > 1e-4) {
        applyLimits(nx, rpmX);
        int32_t t = (int32_t)llround(xMm * countsPerMm(0));
        estMs = std::fmax(estMs, nx.Motion.MovePosnDurationMsec(t, true));
        nx.Motion.MoveWentDone();
        nx.Motion.MovePosnStart(t, true);
        moving.push_back(0);
    }
    if (std::fabs(dy) > 1e-4) {
        applyLimits(ny, rpmY);
        int32_t t = (int32_t)llround(yMm * countsPerMm(1));
        estMs = std::fmax(estMs, ny.Motion.MovePosnDurationMsec(t, true));
        ny.Motion.MoveWentDone();
        ny.Motion.MovePosnStart(t, true);
        moving.push_back(1);
    }
    // Limit czasu z zapasem — liczony z oszacowania biblioteki, nie z własnego
    // wzoru, żeby błąd w przeliczniku jednostek nie objawiał się jako timeout.
    waitMoves(moving, estMs * 1.5 + 3000.0, fd, pending);
}

/* Bazowanie. Jeśli homing nie został skonfigurowany w ClearView (a bez
   Windowsa nie został), robimy zerowanie programowe: bieżąca pozycja staje
   się zerem. To wystarcza na stole warsztatowym, ale NIE jest bazowaniem —
   na maszynie z mechaniką trzeba skonfigurować homing w ClearView. */
static void doHome(int fd, std::string &pending) {
    state = State::HOMING;
    enableAxes({0, 1, 2});
    bool anyReal = false;
    for (size_t i = 0; i < port->NodeCount(); i++) {
        INode &n = port->Nodes(i);
        if (n.Motion.Homing.HomingValid()) {
            anyReal = true;
            n.Motion.Homing.Initiate();
        }
    }
    if (anyReal) {
        double deadline = mgr->TimeStampMsec() + 60000;
        for (size_t i = 0; i < port->NodeCount(); i++) {
            INode &n = port->Nodes(i);
            if (!n.Motion.Homing.HomingValid()) continue;
            while (!n.Motion.Homing.WasHomed()) {
                if (!safetyEnabled()) {
                    stopAll("utrata sygnału zezwolenia w trakcie bazowania");
                    throw std::string("utrata sygnału zezwolenia");
                }
                if (mgr->TimeStampMsec() > deadline) {
                    stopAll("bazowanie nie zakończyło się w czasie");
                    throw std::string("bazowanie nie zakończyło się w czasie");
                }
            }
        }
    }
    // osie bez skonfigurowanego homingu: zerowanie programowe
    for (size_t i = 0; i < port->NodeCount(); i++) {
        INode &n = port->Nodes(i);
        if (!n.Motion.Homing.HomingValid())
            n.Motion.AddToPosition(-n.Motion.PosnMeasured.Value());
    }
    // Po bazowaniu oś stoi w punkcie bazowania, czyli w zerze. Jeśli zero
    // wypada poza limitami programowymi, maszyna od razu jest poza zakresem —
    // to błąd konfiguracji osi, a nie stan do przemilczenia.
    for (int a = 0; a < 3; a++)
        if (axCfg[a].limits && (axCfg[a].softMin > 0.0 || axCfg[a].softMax < 0.0))
            printf("UWAGA: oś %s — punkt bazowania (zero) leży poza limitami "
                   "programowymi %.3f..%.3f mm\n",
                   axes[a].name, axCfg[a].softMin, axCfg[a].softMax);
    (void)fd; (void)pending;
    state = State::READY;
}

/* Numer wyjścia zajętego przez wrzeciono, albo -1 gdy SPINDLE_OUTPUT=none. */
static int spindleOutputIndex() {
    if (cfg.spindleOutput == "brake0") return 0;
    if (cfg.spindleOutput == "brake1") return 1;
    return -1;
}

/* Ustawia wyjście huba. Wyjścia są nominalnie hamulcowe (BrakeControl), ale
   przy silnikach bez hamulców to zwykłe wyjścia 24 VDC / 500 mA — używamy ich
   do wrzeciona, podajnika, wyrzutnika i sygnalizacji.

   UWAGA (obciążalność): 500 mA na wyjście. Stycznika nie wolno podłączać
   bezpośrednio — tylko przez przekaźnik pośredniczący. Instrukcja
   ClearPath-SC rev. 1.45, str. 47; patrz docs/plan-rozwoju.md, temat J. */
static void setOutput(int idx, bool on) {
    if (idx < 0 || idx > 1) return;
    if (port) port->BrakeControl.BrakeSetting(idx, on ? GPO_ON : GPO_OFF);
    outputState[idx] = on;
}

/* Oba wyjścia w stan wyłączony — wołane raz, zaraz po otwarciu portu.

   Powód nie jest kosmetyczny: producent ostrzega, że system operacyjny może
   przypadkowo załączyć wyjście, gdy aplikacja nie trzyma portu, a u nas ten
   scenariusz realnie występuje (cdc_acm przejmuje hub przy każdej ponownej
   enumeracji USB — ryzyko A w docs/mozliwosci-clearpath-sc.md). Start mostka
   ma więc ustalić znany stan, a nie go odziedziczyć.

   To NIE zastępuje obwodu bezpieczeństwa: sygnał do regulatora wrzeciona i tak
   musi iść szeregowo przez styk osłon. */
static void resetOutputs() {
    setOutput(0, false);
    setOutput(1, false);
    spindleOn = false;
}

static void setSpindle(bool on) {
    const int idx = spindleOutputIndex();
    if (idx >= 0) setOutput(idx, on);
    // "none": brak podłączonego wyjścia — śledzimy tylko stan
    spindleOn = on;
}

// --- protokół --------------------------------------------------------------

static std::string statusLine() {
    // REL: litery osi zluzowanych, "-" gdy żadna
    std::string rel;
    for (int a = 0; a < 3; a++)
        if (axisReleased[a]) rel += axes[a].name;
    if (rel.empty()) rel = "-";

    char buf[256];
    snprintf(buf, sizeof(buf),
             "OK STATE=%s EN=%d X=%.3f Y=%.3f Z=%.3f SP=%d REL=%s OUT=%d%d",
             stateName(state), safetyEnabled() ? 1 : 0,
             port ? posMm(0) : 0.0, port ? posMm(1) : 0.0, port ? posMm(2) : 0.0,
             spindleOn ? 1 : 0, rel.c_str(),
             outputState[0] ? 1 : 0, outputState[1] ? 1 : 0);
    std::string line = buf;

    // Powód alarmu jako ostatnie pole — tekst ze spacjami, więc wszystko po
    // "MSG=" jest treścią. Bez tego operator widziałby ALARM bez wyjaśnienia.
    if (!alarmMsg.empty()) {
        std::string msg = alarmMsg;
        for (char &ch : msg)
            if (ch == '\n' || ch == '\r') ch = ' ';
        line += " MSG=" + msg;
    }
    return line;
}

static void requireEnable() {
    if (!safetyEnabled())
        throw std::string("brak sygnału zezwolenia z systemu bezpieczeństwa — ruch zablokowany");
}

/* Rozwija argument komendy RELEASE/HOLD: "X"/"Y"/"Z" albo "ALL". */
static std::vector<int> axisSpec(const std::string &s) {
    if (s == "ALL" || s == "all") return {0, 1, 2};
    for (int a = 0; a < 3; a++)
        if (s == axes[a].name || (s.size() == 1 && toupper(s[0]) == axes[a].name[0]))
            return {a};
    throw std::string("nieznana oś: ") + s + " (oczekiwano X, Y, Z albo ALL)";
}

static int axisByName(const std::string &s) {
    if (s == "X" || s == "x") return 0;
    if (s == "Y" || s == "y") return 1;
    if (s == "Z" || s == "z") return 2;
    return -1;
}

/* Rozbicie linii na słowa — do komend z parametrami KLUCZ=WARTOSC. */
static std::vector<std::string> tokens(const std::string &s) {
    std::vector<std::string> out;
    size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && isspace((unsigned char)s[i])) i++;
        size_t j = i;
        while (j < s.size() && !isspace((unsigned char)s[j])) j++;
        if (j > i) out.push_back(s.substr(i, j - i));
        i = j;
    }
    return out;
}

/* Wykonuje ruch w stanie RUNNING i przywraca stan poprzedni.
   Maszyna niebazowana zostaje niebazowana: jazda ręczna nie może zostawić
   stanu READY, bo wtedy START ruszyłby program w nieznanym układzie
   współrzędnych. Alarm ustawia własny stan i nie jest tu nadpisywany. */
template <typename F>
static void runMove(F fn) {
    State before = state;
    state = State::RUNNING;
    try {
        fn();
    } catch (...) {
        if (state == State::RUNNING) state = before;
        throw;
    }
    state = (before == State::NOT_HOMED) ? State::NOT_HOMED : State::READY;
}

/* Wykonuje jedną komendę. Zwraca odpowiedź albo pusty string, jeśli
   odpowiedź ma zostać pominięta (ruch przerwany przez STOP). */
static std::string handle(const std::string &line, int fd, std::string &pending) {
    char cmd[32] = {0};
    if (sscanf(line.c_str(), "%31s", cmd) != 1) return "ERR pusta komenda";
    std::string c(cmd);

    try {
        if (c == "PING") return "OK PONG";
        if (c == "STATUS") return statusLine();

        if (c == "STOP") {
            stopAll("zatrzymano przyciskiem STOP");
            setSpindle(false);
            return "OK zatrzymano";
        }
        if (c == "RESET") {
            for (size_t i = 0; i < port->NodeCount(); i++) {
                port->Nodes(i).Status.AlertsClear();
                port->Nodes(i).Motion.NodeStopClear();
            }
            alarmMsg.clear();
            state = State::NOT_HOMED;
            return "OK";
        }
        // RELEASE/HOLD celowo przed bramką ALARM — po alarmie operator często
        // potrzebuje właśnie zluzować oś, żeby ruszyć nią ręcznie.
        if (c == "RELEASE" || c == "HOLD") {
            char ax[8] = {0};
            if (sscanf(line.c_str(), "%*s %7s", ax) != 1)
                return "ERR zła składnia: " + c + " <X/Y/Z/ALL>";
            bool release = (c == "RELEASE");
            if (!release) requireEnable();  // zaciśnięcie = załączenie momentu
            setReleased(axisSpec(ax), release);
            return "OK";
        }
        // AXCFG celowo przed bramką ALARM: serwer wysyła konfigurację osi po
        // każdym połączeniu, także wtedy, gdy maszyna czeka na RESET.
        if (c == "AXCFG") {
            std::vector<std::string> tk = tokens(line);
            if (tk.size() < 3)
                return "ERR zła składnia: AXCFG <X/Y/Z> MMREV=.. [SOFTMIN=.. SOFTMAX=..] "
                       "[LEN=..] [HOME=..]";
            int a = axisByName(tk[1]);
            if (a < 0) return "ERR nieznana oś: " + tk[1];

            AxisCfg nc = axCfg[a];
            bool haveMin = false, haveMax = false;
            for (size_t i = 2; i < tk.size(); i++) {
                size_t eq = tk[i].find('=');
                if (eq == std::string::npos)
                    return "ERR AXCFG: oczekiwano KLUCZ=WARTOSC, jest: " + tk[i];
                std::string key = tk[i].substr(0, eq), val = tk[i].substr(eq + 1);
                if (key == "MMREV") nc.mmPerRev = atof(val.c_str());
                else if (key == "SOFTMIN") { nc.softMin = atof(val.c_str()); haveMin = true; }
                else if (key == "SOFTMAX") { nc.softMax = atof(val.c_str()); haveMax = true; }
                else if (key == "LEN") nc.length = atof(val.c_str());
                else if (key == "HOME") nc.home = val;
                else return "ERR AXCFG: nieznany parametr " + key;
            }
            if (!(nc.mmPerRev > 0))
                return "ERR AXCFG: MMREV (mm na obrót) musi być większe od zera";
            if (haveMin != haveMax)
                return "ERR AXCFG: SOFTMIN i SOFTMAX trzeba podać razem";
            if (haveMin) {
                if (nc.softMin >= nc.softMax)
                    return "ERR AXCFG: SOFTMIN musi być mniejsze od SOFTMAX";
                nc.limits = true;
            }
            axCfg[a] = nc;
            printf("oś %s: %.4f mm/obr, limity %.3f..%.3f mm, długość %.3f mm, baza %s\n",
                   axes[a].name, nc.mmPerRev, nc.softMin, nc.softMax, nc.length,
                   nc.home.c_str());
            return "OK";
        }
        if (c == "SPINDLE") {
            int on = 0; double rpm = 0;
            sscanf(line.c_str(), "%*s %d %lf", &on, &rpm);
            if (on) requireEnable();
            setSpindle(on != 0);
            return "OK";
        }
        if (c == "OUTPUT") {
            // OUTPUT <0|1> <0|1> — wyjście huba (podajnik, wyrzutnik, lampka).
            // Celowo obsługiwane tak samo jak SPINDLE, czyli TAKŻE w stanie
            // ALARM: wyłączenie wyjścia musi być możliwe wtedy, gdy najbardziej
            // się przydaje. Załączenie dalej wymaga zezwolenia.
            int idx = -1, on = -1;
            if (sscanf(line.c_str(), "%*s %d %d", &idx, &on) != 2)
                return "ERR zła składnia: OUTPUT <0|1> <0|1>";
            if (idx != 0 && idx != 1)
                return "ERR OUTPUT: numer wyjścia to 0 albo 1";
            if (on != 0 && on != 1)
                return "ERR OUTPUT: stan to 0 (wyłącz) albo 1 (załącz)";
            if (idx == spindleOutputIndex())
                return "ERR OUTPUT: wyjście " + std::to_string(idx) +
                       " jest zajęte przez wrzeciono (SPINDLE_OUTPUT=" +
                       cfg.spindleOutput + ") — steruj nim komendą SPINDLE";
            if (on) requireEnable();
            setOutput(idx, on != 0);
            return "OK";
        }

        if (state == State::ALARM)
            return "ERR maszyna w stanie ALARM — wykonaj RESET (" + alarmMsg + ")";

        if (c == "HOME") {
            requireEnable();
            doHome(fd, pending);
            return "OK";
        }
        if (c == "MOVEXY") {
            double x, y, feed;
            if (sscanf(line.c_str(), "%*s %lf %lf %lf", &x, &y, &feed) != 3)
                return "ERR zła składnia: MOVEXY <x> <y> <posuw>";
            requireEnable();
            enableAxes({0, 1});
            runMove([&] { moveXY(x, y, feed, fd, pending); });
            return "OK";
        }
        if (c == "MOVEZ") {
            double z, feed;
            if (sscanf(line.c_str(), "%*s %lf %lf", &z, &feed) != 2)
                return "ERR zła składnia: MOVEZ <z> <posuw>";
            requireEnable();
            enableAxes({2});
            runMove([&] { moveAxisAbs(2, z, feed, fd, pending); });
            return "OK";
        }
        if (c == "JOG") {
            char ax[8] = {0}; double dist, feed;
            if (sscanf(line.c_str(), "%*s %7s %lf %lf", ax, &dist, &feed) != 3)
                return "ERR zła składnia: JOG <X/Y/Z> <dystans> <posuw>";
            int a = axisByName(ax);
            if (a < 0) return std::string("ERR nieznana oś: ") + ax;
            requireEnable();
            enableAxes({a});
            runMove([&] { moveAxisAbs(a, posMm(a) + dist, feed, fd, pending); });
            return "OK";
        }
        return "ERR nieznana komenda: " + c;
    } catch (Reject &r) {
        // odrzucenie komendy, nie awaria — maszyna zostaje w dotychczasowym
        // stanie i nie wymaga RESET-u
        return "ERR " + r.msg;
    } catch (std::string &err) {
        if (moveAbortedByStop) {
            // STOP przyszedł w trakcie ruchu: linię STOP skonsumował
            // pollDuringMove, więc to jest JEDYNA odpowiedź, jaką wyślemy.
            // Klient, który zlecił ruch, jest już anulowany i jej nie czyta —
            // odbierze ją żądanie STOP. Zwrócenie pustki zawieszało serwer
            // na oczekiwaniu odpowiedzi, której nikt nie wysyłał.
            moveAbortedByStop = false;
            return "OK zatrzymano";
        }
        if (state != State::ALARM) setAlarm(err);
        return "ERR " + err;
    } catch (mnErr &e) {
        setAlarm(std::string("błąd sFoundation: ") + e.ErrorMsg);
        return std::string("ERR ") + e.ErrorMsg;
    }
}

/* Nasłuch gniazda w trakcie ruchu. Zwraca true, jeśli przyszedł STOP.
   Inne komendy trafiają do `pending` i zostaną obsłużone po ruchu —
   z wyjątkiem STATUS, na który odpowiadamy od razu. */
static bool pollDuringMove(int fd, std::string &pending) {
    fd_set rd;
    FD_ZERO(&rd);
    FD_SET(fd, &rd);
    struct timeval tv = {0, 20000};  // 20 ms
    if (select(fd + 1, &rd, nullptr, nullptr, &tv) <= 0) return false;

    char buf[512];
    ssize_t n = recv(fd, buf, sizeof(buf) - 1, MSG_DONTWAIT);
    if (n <= 0) return false;
    buf[n] = 0;
    pending += buf;

    size_t nl;
    while ((nl = pending.find('\n')) != std::string::npos) {
        std::string line = pending.substr(0, nl);
        pending.erase(0, nl + 1);
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        if (line.rfind("STOP", 0) == 0) return true;
        if (line.rfind("STATUS", 0) == 0) {
            std::string r = statusLine() + "\n";
            send(fd, r.c_str(), r.size(), MSG_NOSIGNAL);
        }
        // pozostałe komendy w trakcie ruchu są ignorowane
    }
    return false;
}

// --- otwarcie sprzętu ------------------------------------------------------

static void openHardware() {
    // wartości startowe osi; serwer nadpisze je komendą AXCFG
    for (int a = 0; a < 3; a++)
        if (axCfg[a].mmPerRev <= 0) axCfg[a].mmPerRev = cfg.mmPerRev;

    std::vector<std::string> hubs;
    SysManager::FindComHubPorts(hubs);
    if (hubs.empty())
        throw std::string("nie znaleziono SC4-Hub — sprawdź USB, zasilanie 24 V "
                          "i przypięcie sterownika (tools/sc4hub-rebind.sh)");

    mgr = SysManager::Instance();
    mgr->ComHubPort(0, hubs[0].c_str());
    mgr->PortsOpen(1);
    port = &mgr->Ports(0);

    if (port->NodeCount() < 3)
        throw std::string("oczekiwano 3 serw, znaleziono " + std::to_string(port->NodeCount()));

    // Rozdzielczość czytamy z serwa — zgadywanie tej stałej daje ruch
    // o zły rząd wielkości, przy poprawnie wyglądającym odczycie pozycji.
    {
        uint32_t res0 = port->Nodes(0).Info.PositioningResolution.Value();
        for (size_t i = 1; i < (size_t)port->NodeCount(); i++) {
            uint32_t r = port->Nodes(i).Info.PositioningResolution.Value();
            if (r != res0)
                throw std::string("serwa mają różne rozdzielczości (" +
                                  std::to_string(res0) + " vs " + std::to_string(r) +
                                  ") — ustaw COUNTS_PER_REV ręcznie");
        }
        if (cfg.countsPerRev <= 0) cfg.countsPerRev = res0;
        else if (cfg.countsPerRev != res0)
            printf("UWAGA: COUNTS_PER_REV=%.0f nadpisuje odczyt z serwa (%u)\n",
                   cfg.countsPerRev, res0);
    }

    // mapowanie osi po numerach seryjnych, jeśli podano w środowisku
    const char *envNames[3] = {"AXIS_X_SERIAL", "AXIS_Y_SERIAL", "AXIS_Z_SERIAL"};
    for (int a = 0; a < 3; a++) {
        const char *want = getenv(envNames[a]);
        if (!want || !*want) continue;
        bool found = false;
        for (size_t i = 0; i < port->NodeCount(); i++) {
            if (std::to_string(port->Nodes(i).Info.SerialNumber.Value()) == want) {
                axes[a].nodeIndex = i;
                found = true;
                break;
            }
        }
        if (!found)
            throw std::string("nie znaleziono serwa o numerze seryjnym ") + want +
                  " (" + envNames[a] + ")";
    }

    printf("SC4-Hub otwarty, węzłów: %d\n", (int)port->NodeCount());
    for (int a = 0; a < 3; a++)
        printf("  oś %s -> Node[%zu]  S/N %d\n", axes[a].name, axes[a].nodeIndex,
               port->Nodes(axes[a].nodeIndex).Info.SerialNumber.Value());
    printf("  rozdzielczość: %.0f imp/obr\n", cfg.countsPerRev);
    for (int a = 0; a < 3; a++)
        printf("  oś %s: %.4f mm/obr => %.1f imp/mm, limity programowe: %s\n",
               axes[a].name, axCfg[a].mmPerRev, countsPerMm(a),
               axCfg[a].limits ? "z serwera" : "BRAK (czekam na AXCFG)");
    printf("  limit obrotów: %.0f obr/min, przysp.: %.0f obr/min/s\n", cfg.maxRpm,
           cfg.accRpmPerSec);
    // znany stan wyjść zamiast odziedziczonego — powód w resetOutputs()
    resetOutputs();
    printf("  wyjście wrzeciona: %s\n", cfg.spindleOutput.c_str());
    {
        const int si = spindleOutputIndex();
        printf("  wyjścia huba: BRAKE_0 %s, BRAKE_1 %s (wyzerowane przy starcie)\n",
               si == 0 ? "= wrzeciono" : "wolne (komenda OUTPUT)",
               si == 1 ? "= wrzeciono" : "wolne (komenda OUTPUT)");
    }
    printf("  zezwolenie (Global Stop): %s\n", safetyEnabled() ? "aktywne" : "BRAK");
    state = State::NOT_HOMED;
}

// --- tryb identyfikacji osi ------------------------------------------------

static int runIdentify() {
    openHardware();
    printf("\nTryb identyfikacji. Każde serwo wykona obrót tam i z powrotem.\n"
           "Zanotuj, które fizycznie się kręci.\n\n");
    for (size_t i = 0; i < port->NodeCount(); i++) {
        INode &n = port->Nodes(i);
        printf("Node[%zu]  S/N %d  — Enter, żeby ruszyć... ", i, n.Info.SerialNumber.Value());
        fflush(stdout);
        while (getchar() != '\n') {}

        n.Status.AlertsClear();
        n.Motion.NodeStopClear();
        n.EnableReq(true);
        double t = mgr->TimeStampMsec() + 3000;
        while (!n.Motion.IsReady() && mgr->TimeStampMsec() < t) {}

        applyLimits(n, 120);
        int32_t rev = (int32_t)cfg.countsPerRev;
        n.Motion.MoveWentDone();
        n.Motion.MovePosnStart(rev, false);
        while (!n.Motion.MoveIsDone()) {}
        mgr->Delay(300);
        n.Motion.MoveWentDone();
        n.Motion.MovePosnStart(-rev, false);
        while (!n.Motion.MoveIsDone()) {}
        n.EnableReq(false);
        printf("  gotowe. To serwo ma S/N %d\n\n", n.Info.SerialNumber.Value());
    }
    printf("Mapowanie ustawia się zmiennymi:\n"
           "  AXIS_X_SERIAL=... AXIS_Y_SERIAL=... AXIS_Z_SERIAL=...\n");
    mgr->PortsClose();
    return 0;
}

// --- serwer TCP ------------------------------------------------------------

static volatile sig_atomic_t stopRequested = 0;
static void onSignal(int) { stopRequested = 1; }

/* Sygnał bez SA_RESTART: inaczej accept()/recv() są wznawiane automatycznie
   i mostek ignoruje SIGTERM — trzeba go było ubijać SIGKILL-em, przez co
   port szeregowy zostawał zajęty i kolejny start kończył się błędem
   inicjalizacji portu. */
static void installSignal(int sig) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = onSignal;
    sa.sa_flags = 0;
    sigaction(sig, &sa, nullptr);
}

static int serve() {
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    int yes = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(cfg.port);
    inet_pton(AF_INET, cfg.bind.c_str(), &addr.sin_addr);

    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }
    listen(srv, 1);
    printf("\nMostek nasłuchuje na %s:%d — ustaw w serwerze:\n"
           "  MACHINE_MODE=clearcore CLEARCORE_HOST=%s CLEARCORE_PORT=%d\n\n",
           cfg.bind.c_str(), cfg.port, cfg.bind.c_str(), cfg.port);

    while (!stopRequested) {
        int fd = accept(srv, nullptr, nullptr);
        if (fd < 0) break;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
        printf("klient połączony\n");

        std::string pending;
        while (!stopRequested) {
            size_t nl;
            while ((nl = pending.find('\n')) == std::string::npos) {
                char buf[512];
                ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
                if (n <= 0) goto disconnected;
                buf[n] = 0;
                pending += buf;
            }
            {
                std::string line = pending.substr(0, nl);
                pending.erase(0, nl + 1);
                while (!line.empty() && (line.back() == '\r' || line.back() == ' '))
                    line.pop_back();
                if (line.empty()) continue;

                std::string reply = handle(line, fd, pending);
                if (!reply.empty()) {
                    reply += "\n";
                    if (send(fd, reply.c_str(), reply.size(), MSG_NOSIGNAL) < 0)
                        goto disconnected;
                }
            }
        }
    disconnected:
        printf("klient rozłączony\n");
        close(fd);
        // Bezpieczny stan po utracie połączenia z serwerem maszyny. Alarm tylko
        // wtedy, gdy maszyna była w ruchu — rozłączenie na postoju nie powinno
        // wymuszać RESET-u przy każdym ponownym połączeniu.
        if (port) {
            if (state == State::RUNNING || state == State::HOMING)
                stopAll("utracono połączenie z serwerem maszyny w trakcie ruchu");
            setSpindle(false);
            disableNodes();
        }
    }
    close(srv);
    return 0;
}

int main(int argc, char **argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);  // log liniowo także przy przekierowaniu
    installSignal(SIGINT);
    installSignal(SIGTERM);
    signal(SIGPIPE, SIG_IGN);

    bool identify = false, list = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--identify")) identify = true;
        else if (!strcmp(argv[i], "--list")) list = true;
        else {
            printf("użycie: %s [--identify] [--list]\n", argv[0]);
            return 2;
        }
    }

    try {
        if (identify) return runIdentify();

        openHardware();
        if (list) { mgr->PortsClose(); return 0; }

        int rc = serve();
        setSpindle(false);
        disableNodes();
        mgr->PortsClose();
        printf("mostek zatrzymany\n");
        return rc;
    } catch (std::string &err) {
        fprintf(stderr, "BŁĄD: %s\n", err.c_str());
        return 1;
    } catch (mnErr &e) {
        fprintf(stderr, "BŁĄD sFoundation: addr=%d, err=0x%08x\n%s\n", e.TheAddr,
                e.ErrorCode, e.ErrorMsg);
        return 1;
    }
}
