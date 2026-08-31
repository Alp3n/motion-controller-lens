"""Warstwa maszyny: wspólny interfejs, symulator oraz łącze do mostka SC4-Hub.

Serwer rozmawia z maszyną wyłącznie przez klasę bazową Machine, więc panel,
API i integracja MES działają identycznie na symulatorze (MACHINE_MODE=sim)
i na sprzęcie (MACHINE_MODE=sc4hub).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from enum import Enum

from .axes import REQUIRED_AXES, AxisConfig
from .axes import home_groups as axis_home_groups
from .cycle import (
    OUTPUT_NAMES,
    STEP_MOVE,
    STEP_OUTPUT,
    STEP_PAUSE,
    STEP_PROGRAM,
    STEP_SMART,
    Cycle,
    CycleStep,
    empty_cycle,
)
from .profiles import PROFILE_GLOBAL, AxisParams, ParameterProfile
from .smart import SmartDefinition
from .spindle import SpindleConfig
from .program import Operation, Program, cut_path, pass_depths


class MachineState(str, Enum):
    INIT = "INIT"
    NOT_HOMED = "NOT_HOMED"
    HOMING = "HOMING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ALARM = "ALARM"


@dataclass
class MachineStatus:
    state: MachineState = MachineState.INIT
    safety_enable: bool = False
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    spindle_on: bool = False
    program_number: str | None = None
    program_name: str | None = None
    order_id: str | None = None
    current_op: int | None = None  # LP aktualnej operacji
    total_ops: int = 0
    alarm_message: str = ""
    # osie zluzowane (moment zdjęty, da się ruszyć ręcznie), np. ["z"]
    released_axes: list[str] = field(default_factory=list)
    # cykl maszyny: LP wykonywanego kroku i ich łączna liczba
    cycle_step: int | None = None
    total_cycle_steps: int = 0
    # tryb automatyczny (temat F): cykl powtarza się bez zatrzymania, dopóki
    # nie przerwie go STOP, błąd albo utrata sygnału zezwolenia
    cycle_loop: bool = False
    # wyjścia cyfrowe sterowane z cyklu (podajnik, wyrzutnik, lampka)
    outputs: dict[str, bool] = field(
        default_factory=lambda: {name: False for name in OUTPUT_NAMES}
    )
    # profil parametrów ruchu obowiązujący w tej chwili
    active_profile: str = ""
    # obciążenie osi [% momentu maksymalnego] — podstawa funkcji SMART
    torque: dict[str, float] = field(
        default_factory=lambda: {a: 0.0 for a in REQUIRED_AXES}
    )
    # skąd pochodzi `torque`: "sterownik" (realny pomiar), "symulacja"
    # (wyliczone przez symulator — NIE jest pomiarem) albo "brak"
    torque_source: str = "brak"

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "safety_enable": self.safety_enable,
            "position": {"x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3)},
            "spindle_on": self.spindle_on,
            "program_number": self.program_number,
            "program_name": self.program_name,
            "order_id": self.order_id,
            "current_op": self.current_op,
            "total_ops": self.total_ops,
            "alarm_message": self.alarm_message,
            "released_axes": sorted(self.released_axes),
            "cycle_step": self.cycle_step,
            "total_cycle_steps": self.total_cycle_steps,
            "cycle_loop": self.cycle_loop,
            "outputs": dict(self.outputs),
            "active_profile": self.active_profile,
            "torque": {a: round(v, 1) for a, v in self.torque.items()},
            "torque_source": self.torque_source,
        }


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


class MachineError(Exception):
    """Błąd operacji maszynowej — komunikat po polsku dla operatora."""


class Machine:
    """Wspólny interfejs maszyny (symulator i sprzęt)."""

    def __init__(self) -> None:
        self.status = MachineStatus()
        self._program: Program | None = None
        self._resume_event = asyncio.Event()
        # konfiguracja osi z ekranu „Konfiguracja osi" — limity programowe
        # i przełożenia; pusta oznacza brak ograniczeń po stronie serwera
        self.axes: dict[str, AxisConfig] = {}
        # profile parametrów ruchu; pusty słownik = brak ograniczeń z profilu
        self.profiles: dict[str, ParameterProfile] = {}
        self.active_profile: str = PROFILE_GLOBAL
        self.status.active_profile = PROFILE_GLOBAL
        # cykl maszyny (poziom admina) — pusty, dopóki nie zostanie zdefiniowany
        self.cycle: Cycle = empty_cycle()
        # wrzeciono: kiedy się załącza i kiedy gaśnie (app/spindle.py).
        # Wartości domyślne odtwarzają zachowanie sprzed tej konfiguracji.
        self.spindle: SpindleConfig = SpindleConfig()
        # definicje SMART (nazwa -> zestaw parametrów procedury); wspólne dla
        # programu technologa i cyklu maszyny — celowo jeden zbiór, żeby ta
        # sama nazwa znaczyła to samo w obu miejscach
        self.smart: dict[str, SmartDefinition] = {}

    # --- konfiguracja wrzeciona (wspólna) ---------------------------------

    def apply_spindle_config(self, cfg: SpindleConfig) -> None:
        self.spindle = cfg

    # --- konfiguracja osi (wspólna) ---------------------------------------

    def apply_axis_config(self, axes: dict[str, AxisConfig]) -> None:
        """Podmienia konfigurację osi; podklasy dosyłają ją do sprzętu."""
        self.axes = dict(axes)

    def apply_smart(self, definitions: dict[str, SmartDefinition]) -> None:
        """Podmienia definicje SMART widoczne dla programu i cyklu."""
        self.smart = dict(definitions)

    def _smart_definition(self, name: str) -> SmartDefinition:
        definition = self.smart.get(name or "")
        if definition is None:
            known = ", ".join(sorted(self.smart)) or "brak zdefiniowanych"
            raise MachineError(
                f"nie ma definicji SMART '{name}' — zdefiniuj ją na ekranie "
                f"„Funkcje SMART” (dostępne: {known})"
            )
        return definition

    # --- profile parametrów ruchu (wspólne) -------------------------------

    def apply_profiles(
        self, profiles: dict[str, ParameterProfile], active: str
    ) -> None:
        """Podmienia zestaw profili i wskazuje aktywny."""
        self.profiles = dict(profiles)
        self._set_profile(active)

    def _set_profile(self, name: str) -> None:
        """Ustawia aktywny profil bez walidacji stanu — do użytku wewnętrznego.

        Używane przy przywracaniu profilu po programie detalu, gdzie maszyna
        z definicji jest jeszcze w ruchu.
        """
        self.active_profile = name
        self.status.active_profile = name

    def set_active_profile(self, name: str) -> None:
        """Przełącza aktywny profil — odrzucane w ruchu, jak zmiana limitów osi."""
        if self.status.state in (MachineState.RUNNING, MachineState.HOMING):
            raise MachineError("nie można zmienić profilu w trakcie ruchu maszyny")
        if name not in self.profiles:
            raise MachineError(
                f"nieznany profil '{name}' — dostępne: "
                + ", ".join(sorted(self.profiles))
            )
        self._set_profile(name)

    # --- cykl maszyny (wspólny) -------------------------------------------

    def apply_cycle(self, cycle: Cycle) -> None:
        """Podmienia definicję cyklu maszyny."""
        self.cycle = cycle
        self.status.total_cycle_steps = len(cycle.steps)

    async def start_cycle(self, loop: bool = False) -> None:
        raise NotImplementedError

    def axis_params(self, axis: str) -> AxisParams | None:
        """Parametry osi z aktywnego profilu; None = profil jej nie opisuje."""
        profile = self.profiles.get(self.active_profile)
        if profile is None:
            return None
        return profile.axes.get(axis)

    def _capped_feed(self, feed: float, axes: list[str]) -> float:
        """Posuw ograniczony prędkością maksymalną z aktywnego profilu.

        Ruch obejmuje kilka osi naraz, więc obowiązuje najniższy limit
        spośród nich — oś o najwolniejszym limicie wyznacza tempo całości.
        """
        limits = [
            p.vel_max for p in (self.axis_params(a) for a in axes) if p is not None
        ]
        if not limits:
            return feed
        return min(feed, min(limits))

    def axis_jog_feed(self, axis: str) -> float:
        """Domyślna prędkość JOG skonfigurowana dla osi (ekran /axes)."""
        cfg = self.axes.get(axis)
        return cfg.vel_jog if cfg is not None else 500.0

    def home_groups(self) -> list[list[str]]:
        """Osie do zbazowania w kolejności z konfiguracji (ekran /homing).

        Zwraca tylko osie, którymi symulator umie ruszyć (X/Y/Z) — oś dodatkowa
        z ustawioną kolejnością jest pomijana, bo nie ma dla niej komendy ruchu.
        Bez wczytanej konfiguracji osi wracamy do dawnej sekwencji na sztywno:
        najpierw X i Y, potem Z.
        """
        if not self.axes:
            return [["x", "y"], ["z"]]
        groups = []
        for group in axis_home_groups(self.axes):
            movable = [axis for axis in group if axis in REQUIRED_AXES]
            if movable:
                groups.append(movable)
        return groups

    def _home_feed(self, axes: list[str]) -> float:
        """Prędkość bazowania — najwolniejsza spośród skonfigurowanych osi.

        Dotyczy tylko symulatora: na sprzęcie bazowaniem steruje serwo wg
        ustawień w ClearView, więc `SC4HubMachine` tej wartości nie używa.
        """
        values = [self.axes[a].vel_home for a in axes if a in self.axes]
        return min(values) if values else 1000.0

    def _check_soft_limit(self, axis: str, target: float) -> None:
        """Odrzuca ruch poza limit programowy osi (JOG i ruchy pojedynczej osi).

        Punkty programu są sprawdzane wcześniej, przy jego wczytaniu — tu
        chodzi o ruch ręczny, którego nikt wcześniej nie zweryfikował.
        """
        cfg = self.axes.get(axis)
        if cfg is None:
            return
        if not (cfg.soft_min - 1e-6 <= target <= cfg.soft_max + 1e-6):
            raise MachineError(
                f"oś {axis.upper()}: pozycja {target:.3f} mm poza limitem programowym "
                f"({cfg.soft_min:.3f}..{cfg.soft_max:.3f} mm)"
            )

    # --- ładowanie programu (wspólne) -------------------------------------

    @property
    def program(self) -> Program | None:
        """Załadowany program — do ponownej walidacji po zmianie limitów osi."""
        return self._program

    def load_program(self, program: Program, order_id: str | None) -> None:
        if self.status.state in (MachineState.RUNNING, MachineState.HOMING):
            raise MachineError("nie można zmienić programu w trakcie ruchu maszyny")
        self._program = program
        self.status.program_number = program.number
        self.status.program_name = program.name
        self.status.order_id = order_id
        self.status.total_ops = len(program.operations)
        self.status.current_op = None

    # --- operacje (implementowane w podklasach) ---------------------------

    async def home(self) -> None:
        raise NotImplementedError

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def reset(self) -> None:
        raise NotImplementedError

    async def jog(self, axis: str, distance: float, feed: float) -> None:
        raise NotImplementedError

    async def set_released(self, axes: list[str], released: bool) -> None:
        """Luzuje (zdejmuje moment) lub zaciska wskazane osie."""
        raise NotImplementedError

    @staticmethod
    def _parse_axes(spec: str) -> list[str]:
        """'all' -> wszystkie osie; 'x'/'y'/'z' -> jedna."""
        spec = spec.lower()
        if spec == "all":
            return ["x", "y", "z"]
        if spec not in ("x", "y", "z"):
            raise MachineError(f"nieznana oś: {spec}")
        return [spec]

    def _require_not_released(self, axes: list[str]) -> None:
        blocked = [a for a in axes if a in self.status.released_axes]
        if blocked:
            raise MachineError(
                "osie zluzowane: " + ", ".join(sorted(blocked)).upper()
                + " — zaciśnij je przed ruchem"
            )

    def resume(self) -> None:
        """Wznowienie po operacji PAUZA."""
        self._resume_event.set()

    def _require_enable(self) -> None:
        if not self.status.safety_enable:
            raise MachineError(
                "brak sygnału zezwolenia z systemu bezpieczeństwa — ruch zablokowany"
            )


# --- symulacja obciążenia osi ----------------------------------------------
#
# UWAGA: poniższe liczby są ZMYŚLONE. Nie pochodzą z pomiaru na maszynie ani
# z dokumentacji Teknica — mają tylko dać panelowi i funkcjom SMART przebieg,
# który zachowuje się z grubsza sensownie, zanim mostek zacznie odsyłać realny
# `TrqMeasured` (etap 0 tematu K). Dlatego status niesie osobne pole
# `torque_source`: symulator wpisuje "symulacja", sterownik "sterownik".
#
# NIE WOLNO na tych wartościach dobierać progów siły dla maszyny. Do tego służy
# pomiar na sprzęcie i ekran `/sila` (etap 0 i 2 tematu K) — patrz
# `docs/funkcje-smart.md`.

SIM_TRQ_HOLD = {"x": 0.5, "y": 0.5, "z": 8.0}   # postój [% momentu maks.]
SIM_TRQ_FRICTION = 3.0        # opór ruchu, niezależny od prędkości [%]
SIM_TRQ_PER_1000 = 4.0        # narastanie z prędkością [% na 1000 mm/min]
SIM_TRQ_GRAVITY_Z = 5.0       # asymetria osi Z: w górę drożej, w dół taniej
SIM_TRQ_CUT = 20.0            # dodatek za skrawanie (wrzeciono + Z pod zerem)
SIM_TRQ_CUT_PER_MM = 12.0     # ... rosnący z głębokością [% na mm]


class SimulatedMachine(Machine):
    """Symulator: ruchy w czasie rzeczywistym wg posuwów z programu.

    Pozwala rozwijać i testować panel, API oraz integrację MES bez sprzętu.
    Sygnał zezwolenia można przełączać z panelu (w trybie sprzętowym jest
    tylko do odczytu — pochodzi z wejścia Global Stop na SC4-Hub).
    """

    def __init__(self) -> None:
        super().__init__()
        self.status.state = MachineState.NOT_HOMED
        self.status.safety_enable = True  # symulacja: zezwolenie domyślnie aktywne
        self._run_task: asyncio.Task | None = None
        self._sim_load: dict[str, float] = {}
        self._settle_sim_torque()

    def set_safety_enable(self, enabled: bool) -> None:
        self.status.safety_enable = enabled
        if not enabled and self.status.state in (
            MachineState.RUNNING,
            MachineState.HOMING,
            MachineState.PAUSED,
        ):
            self._abort("utrata sygnału zezwolenia — zatrzymanie awaryjne")

    def _abort(self, message: str) -> None:
        if self._run_task:
            self._run_task.cancel()
            self._run_task = None
        self.status.spindle_on = False
        self.status.state = MachineState.ALARM
        self.status.alarm_message = message

    async def home(self) -> None:
        """Sprawdza warunki i uruchamia bazowanie w tle.

        Walidacja musi być synchroniczna — inaczej błąd wpadłby do zadania
        w tle i endpoint zwróciłby OK mimo nieudanego bazowania.
        """
        if self.status.state in (MachineState.RUNNING, MachineState.HOMING):
            raise MachineError("maszyna jest w ruchu")
        groups = self.home_groups()
        if not groups:
            raise MachineError(
                "żadna oś nie ma ustawionej kolejności bazowania — ustaw ją na "
                "ekranie konfiguracji bazowania"
            )
        self._require_not_released(["x", "y", "z"])
        self._require_enable()
        self.status.state = MachineState.HOMING
        self._run_task = asyncio.create_task(self._do_home(groups))

    async def _do_home(self, groups: list[list[str]]) -> None:
        """Symulacja bazowania: odjazd w górę, potem grupy osi po kolei.

        Zero osi to jej punkt bazowy, więc „zbazowanie" sprowadza się do
        dojechania do zera. `Offset Move` z ekranu bazowania nie ma tu nic do
        roboty — w prawdziwym serwie offset przesuwa punkt, w którym zapada
        zero, a nie pozycję po bazowaniu; patrz docs/zmiany/ekran-bazowania.md.
        """
        try:
            # Odjazd w górę przed jakimkolwiek ruchem w płaszczyźnie XY,
            # niezależnie od skonfigurowanej kolejności — bez tego oś Z mogłaby
            # jechać nad detalem na roboczej wysokości. Odjazd ograniczony
            # limitem programowym Z.
            z_cfg = self.axes.get("z")
            lift = 40.0 if z_cfg is None else min(40.0, z_cfg.soft_max)
            await self._move_to(
                self.status.x, self.status.y, lift, feed=self._home_feed(["z"])
            )
            for group in groups:
                target = {"x": self.status.x, "y": self.status.y, "z": self.status.z}
                for axis in group:
                    target[axis] = 0.0
                await self._move_to(
                    target["x"], target["y"], target["z"], feed=self._home_feed(group)
                )
        except asyncio.CancelledError:
            return
        finally:
            self._run_task = None
        self.status.state = MachineState.READY

    async def start(self) -> None:
        if self.status.state == MachineState.PAUSED:
            self.resume()
            return
        if self.status.state != MachineState.READY:
            raise MachineError(
                f"start możliwy tylko w stanie READY (obecnie: {self.status.state.value})"
            )
        if not self._program:
            raise MachineError("nie załadowano programu — wybierz zlecenie w MES")
        self._require_not_released(["x", "y", "z"])
        self._require_enable()
        self.status.state = MachineState.RUNNING
        self.status.alarm_message = ""
        if self.spindle.start_with_machine:
            self.status.spindle_on = True
        self._run_task = asyncio.create_task(self._run_program())

    async def stop(self) -> None:
        if self._run_task:
            self._run_task.cancel()
            self._run_task = None
        self.status.spindle_on = False
        if self.status.state in (MachineState.RUNNING, MachineState.PAUSED, MachineState.HOMING):
            self.status.state = MachineState.ALARM
            self.status.alarm_message = "zatrzymano przyciskiem STOP"

    async def reset(self) -> None:
        if self.status.state == MachineState.ALARM:
            self.status.alarm_message = ""
            self.status.current_op = None
            self.status.state = MachineState.NOT_HOMED

    async def set_released(self, axes: list[str], released: bool) -> None:
        if self.status.state in (MachineState.RUNNING, MachineState.HOMING):
            raise MachineError("nie można luzować osi w trakcie ruchu maszyny")
        if not released:
            self._require_enable()
        current = set(self.status.released_axes)
        self.status.released_axes = sorted(
            current | set(axes) if released else current - set(axes)
        )

    async def jog(self, axis: str, distance: float, feed: float) -> None:
        if self.status.state not in (MachineState.READY, MachineState.NOT_HOMED):
            raise MachineError("JOG możliwy tylko przy zatrzymanej maszynie")
        self._require_not_released([axis])
        self._require_enable()
        target = {
            "x": self.status.x,
            "y": self.status.y,
            "z": self.status.z,
        }
        if axis not in target:
            raise MachineError(f"nieznana oś: {axis}")
        target[axis] += distance
        self._check_soft_limit(axis, target[axis])
        await self._move_to(target["x"], target["y"], target["z"], feed)

    async def _run_program(self) -> None:
        program = self._program
        assert program is not None
        try:
            await self._run_operations(program)
            self.status.current_op = None
            self.status.state = MachineState.READY
        except asyncio.CancelledError:
            raise
        except MachineError as exc:
            self._abort(str(exc))
        finally:
            self.status.spindle_on = False
            self._run_task = None

    async def _run_operations(self, program: Program) -> None:
        """Same operacje programu detalu + odjazd do pozycji bezpiecznej.

        Wydzielone z `_run_program`, bo krok PROGRAM cyklu maszyny wykonuje
        dokładnie to samo, ale nie kończy pracy maszyny — po nim idą kolejne
        kroki cyklu.
        """
        # Załączenie wrzeciona na starcie programu — jedno miejsce, tak jak
        # w SC4HubMachine (komenda SPINDLE przed pierwszą operacją). Wcześniej
        # robiła to każda operacja skrawająca z osobna, przez co ustawienie
        # „program nie załącza wrzeciona" nie miało jak zadziałać.
        if self.spindle.start_with_program:
            self.status.spindle_on = True
        for op in program.operations:
            self.status.current_op = op.lp
            await self._execute_operation(program, op)
        # odjazd na Z bezpieczne i powrót do bazy
        await self._move_to(
            self.status.x, self.status.y, program.z_safe, program.feed_travel
        )
        await self._move_to(0.0, 0.0, program.z_safe, program.feed_travel)
        # Wyłączenie po programie dotyczy granicy programu detalu, nie końca
        # pracy maszyny — ten drugi gasi wrzeciono zawsze i bezwarunkowo,
        # w `finally` _run_program/_run_cycle, także przy błędzie i STOP.
        if self.spindle.stop_after_program:
            self.status.spindle_on = False

    # --- cykl maszyny -----------------------------------------------------

    async def start_cycle(self, loop: bool = False) -> None:
        """Uruchamia cykl maszyny: jeden przebieg (półautomatyczny, temat F)
        albo pętlę bez zatrzymania (automatyczny), dopóki nie przerwie jej
        STOP, błąd w kroku, albo utrata sygnału zezwolenia — to ostatnie
        obsługuje już `set_safety_enable()`, przerywając `_run_task` tak samo
        jak przy pojedynczym przebiegu.
        """
        if self.status.state == MachineState.PAUSED:
            self.resume()
            return
        if self.status.state != MachineState.READY:
            raise MachineError(
                f"start cyklu możliwy tylko w stanie READY "
                f"(obecnie: {self.status.state.value})"
            )
        if not self.cycle.steps:
            raise MachineError("cykl maszyny nie jest zdefiniowany")
        if self.cycle.uses_program() and not self._program:
            raise MachineError(
                "cykl wywołuje program detalu, a żaden nie jest załadowany "
                "— wybierz zlecenie w MES"
            )
        self._require_not_released(["x", "y", "z"])
        self._require_enable()
        self.status.state = MachineState.RUNNING
        self.status.alarm_message = ""
        self.status.cycle_loop = loop
        if self.spindle.start_with_machine:
            self.status.spindle_on = True
        self._run_task = asyncio.create_task(self._run_cycle(loop))

    async def _run_cycle(self, loop: bool) -> None:
        try:
            while True:
                for step in self.cycle.steps:
                    self.status.cycle_step = step.lp
                    await self._execute_cycle_step(step)
                    # Krok bez realnego ruchu (WYJSCIE, albo RUCH do pozycji,
                    # w której oś już jest) nie zawiesza się na niczym — bez
                    # tego punktu zawieszenia pętla automatyczna nigdy nie
                    # oddałaby sterowania do event loopa i zamroziłaby cały
                    # serwer (znalezione i sprawdzone przy pisaniu testu).
                    await asyncio.sleep(0)
                self.status.cycle_step = None
                self.status.current_op = None
                if not loop:
                    break
            self.status.state = MachineState.READY
        except asyncio.CancelledError:
            raise
        except MachineError as exc:
            self._abort(str(exc))
        finally:
            self.status.spindle_on = False
            self.status.cycle_loop = False
            self._run_task = None

    async def _execute_cycle_step(self, step: CycleStep) -> None:
        """Jeden krok cyklu; profil kroku obowiązuje tylko na czas jego trwania.

        Profil przywracamy w `finally`, więc wraca także przy błędzie
        i przy zatrzymaniu (STOP anuluje zadanie, co tu wchodzi jako
        CancelledError). Bez tego przerwany program detalu zostawiłby maszynę
        na swoich parametrach — np. na 10% momentu — a kolejne kroki cyklu
        pojechałyby z nimi po cichu. Wymóg z DECYZJE_2026-08-25.md §3.
        """
        previous_profile = self.active_profile
        if step.profile and step.profile in self.profiles:
            self._set_profile(step.profile)
        try:
            await self._run_cycle_step_body(step)
        finally:
            self._set_profile(previous_profile)

    async def _run_cycle_step_body(self, step: CycleStep) -> None:
        if step.kind == STEP_PAUSE:
            was_on = self.status.spindle_on  # jak przy operacji PAUZA programu
            self.status.spindle_on = False
            self.status.state = MachineState.PAUSED
            self._resume_event.clear()
            await self._resume_event.wait()
            self.status.state = MachineState.RUNNING
            self.status.spindle_on = was_on
            return

        if step.kind == STEP_OUTPUT:
            self.status.outputs[step.output] = bool(step.output_on)
            return

        if step.kind == STEP_SMART:
            await self._run_smart(step.smart)
            return

        if step.kind == STEP_PROGRAM:
            program = self._program
            if program is None:
                raise MachineError("krok PROGRAM: nie załadowano programu detalu")
            await self._run_operations(program)
            self.status.current_op = None
            return

        # STEP_MOVE — przejazd wskazanych osi; osie pominięte zostają na miejscu
        target = {"x": self.status.x, "y": self.status.y, "z": self.status.z}
        for axis, value in step.targets.items():
            if axis not in target:
                raise MachineError(
                    f"krok {step.lp}: oś {axis.upper()} nie jest obsługiwana "
                    "przez ruch symulatora (dziś tylko X/Y/Z)"
                )
            self._check_soft_limit(axis, value)
            target[axis] = value
        feed = step.feed or 1000.0
        await self._move_to(target["x"], target["y"], target["z"], feed)

    # --- funkcje SMART ----------------------------------------------------

    async def _move_axis(self, axis: str, value: float, feed: float) -> None:
        """Przejazd jednej osi do pozycji bezwzględnej; reszta stoi."""
        target = {"x": self.status.x, "y": self.status.y, "z": self.status.z}
        if axis not in target:
            raise MachineError(
                f"oś {axis.upper()} nie jest obsługiwana przez ruch symulatora "
                "(dziś tylko X/Y/Z)"
            )
        self._check_soft_limit(axis, value)
        target[axis] = value
        await self._move_to(target["x"], target["y"], target["z"], feed)

    async def _run_smart(self, name: str) -> None:
        """Funkcja SMART w symulatorze — RUCH BEZ REALNEJ KONTROLI SIŁY.

        Odtwarza *kształt* procedury `ciecie_adaptacyjne`: dojazd prędkością
        szybką, zwolnienie, gdy obciążenie przekroczy próg zwolnienia, powrót
        do prędkości szybkiej poniżej progu przyspieszenia, zatrzymanie po
        osiągnięciu progu siły i cofnięcie narzędzia.

        Reaguje jednak na moment ZMYŚLONY przez `_sim_torque`, a nie na
        pomiar z silnika, i robi to w Pythonie — czyli dokładnie tak, jak na
        maszynie zrobić się NIE DA (mostek nie oddaje sterowania w trakcie
        ruchu, powód w `docs/funkcje-smart.md`). Służy do sprawdzenia
        przepływu danych i ekranów, nie do dobierania progów siły.
        """
        definition = self._smart_definition(name)
        p = definition.params
        axis = str(p["os"])
        threshold = float(p["sila_pct"])
        distance = float(p["dojazd_mm"])
        retract = float(p["cofniecie_mm"])
        v_fast = float(p["v_szybka"])
        v_slow = float(p["v_wolna"])
        slow_above = threshold * float(p["prog_zwolnienia"])
        fast_below = threshold * float(p["prog_przyspieszenia"])
        collision_at = threshold * float(p["wsp_kolizji"])

        # Odcinek między „odczytami momentu" — tyle, ile mostek przejechałby
        # przy prędkości szybkiej w jednym okresie próbkowania. Zgrubnie, żeby
        # przebieg w symulatorze przypominał ten z maszyny.
        stride = max(0.02, v_fast / 60.0 * float(p["probkowanie_ms"]) / 1000.0)

        start = getattr(self.status, axis)
        direction = 1.0 if distance >= 0 else -1.0
        total = abs(distance)
        travelled = 0.0
        feed = v_fast
        reached = False
        collision = False

        while travelled < total - 1e-9:
            travelled = min(total, travelled + stride)
            await self._move_axis(axis, start + direction * travelled, feed)
            load = self._sim_load.get(axis, 0.0)
            if load >= collision_at:
                collision = True
                break
            if load >= threshold:
                reached = True
                break
            if load >= slow_above:
                feed = v_slow
            elif load <= fast_below:
                feed = v_fast

        if retract > 0 and (reached or collision):
            # przy kolizji cofamy mocniej — narzędzie ma odejść od przeszkody,
            # a nie zostać oparte o nią z pełnym momentem
            back = retract * (3.0 if collision else 1.0)
            await self._move_axis(
                axis, getattr(self.status, axis) - direction * back, v_fast
            )

        if collision:
            raise MachineError(
                f"SMART '{name}': obciążenie osi {axis.upper()} przekroczyło "
                f"{_fmt_pct(collision_at)}% momentu — traktuję to jako kolizję, "
                "narzędzie cofnięte"
            )

    async def _execute_operation(self, program: Program, op: Operation) -> None:
        if op.op_type == "PAUZA":
            # wrzeciono gaśnie na czas pauzy i wraca do stanu sprzed niej —
            # dotąd symulator zostawiał je wyłączone do końca programu, choć
            # SC4HubMachine wysyłał po wznowieniu ponowne SPINDLE 1
            was_on = self.status.spindle_on
            self.status.spindle_on = False
            self.status.state = MachineState.PAUSED
            self._resume_event.clear()
            await self._resume_event.wait()
            self.status.state = MachineState.RUNNING
            self.status.spindle_on = was_on
            return

        if op.op_type == "WRZECIONO":
            self.status.spindle_on = op.rpm > 0
            return

        if op.op_type == "SMART":
            await self._run_smart(op.smart)
            return

        if op.op_type == "SZYBKI":
            # przejazd bez skrawania: zawsze na wysokości bezpiecznej
            feed = op.feed or program.feed_travel
            await self._move_to(
                self.status.x, self.status.y, program.z_safe, program.feed_travel
            )
            await self._move_to(op.x, op.y, program.z_safe, feed)
            return

        feed = op.feed or program.feed_work
        depths = pass_depths(op)
        path = cut_path(op)

        # dojazd nad punkt na wysokości bezpiecznej
        await self._move_to(self.status.x, self.status.y, program.z_safe, program.feed_travel)
        await self._move_to(op.x, op.y, program.z_safe, program.feed_travel)

        for i, depth in enumerate(depths):
            # zagłębienie posuwem roboczym na głębokość tego przejścia
            await self._move_to(op.x, op.y, depth, feed)
            for px, py in path:
                await self._move_to(px, py, depth, feed)
            # wycofanie na Z bezpieczne — przy wielu przejściach daje odprowadzenie wióra
            await self._move_to(self.status.x, self.status.y, program.z_safe, program.feed_travel)
            if path and i < len(depths) - 1:
                # powrót na początek toru przed kolejnym przejściem
                await self._move_to(op.x, op.y, program.z_safe, program.feed_travel)

    # --- zmyślone obciążenie osi (patrz komentarz przy SIM_TRQ_*) ---------

    def _sim_torque(self, axis: str, delta: float, feed: float) -> float:
        """Obciążenie jednej osi [% momentu maks.] — wartość WYMYŚLONA.

        Model: moment postojowy (oś Z trzyma ciężar) + opór ruchu rosnący
        z prędkością + asymetria grawitacyjna Z (w górę drożej niż w dół)
        + dodatek za skrawanie, rosnący z głębokością pod powierzchnią
        materiału (Z < 0). Tyle wystarczy, żeby ekrany pokazywały coś, co
        zmienia się w sposób podobny do prawdy; z prawdą nie ma to nic
        wspólnego poza kształtem.
        """
        value = SIM_TRQ_HOLD.get(axis, 0.5)
        if abs(delta) > 1e-9:
            value += SIM_TRQ_FRICTION + SIM_TRQ_PER_1000 * abs(feed) / 1000.0
            if axis == "z":
                value += SIM_TRQ_GRAVITY_Z if delta > 0 else -SIM_TRQ_GRAVITY_Z
            depth = self.status.z
            if self.status.spindle_on and depth < 0.0:
                value += SIM_TRQ_CUT + SIM_TRQ_CUT_PER_MM * (-depth)
        return max(0.0, min(100.0, value))

    def _update_sim_torque(self, deltas: dict[str, float], feed: float) -> None:
        for axis in ("x", "y", "z"):
            self.status.torque[axis] = self._sim_torque(
                axis, deltas.get(axis, 0.0), feed
            )
        self.status.torque_source = "symulacja"
        if any(abs(d) > 1e-9 for d in deltas.values()):
            # Ostatnie obciążenie *w ruchu*. Pętla SMART czyta właśnie to,
            # a nie `status.torque`: status po zakończeniu odcinka wraca do
            # wartości postojowych, więc odczytany po ruchu wyglądałby tak,
            # jakby narzędzie nagle przestało napotykać opór.
            self._sim_load = dict(self.status.torque)

    def _settle_sim_torque(self) -> None:
        """Maszyna stoi — zostaje sam moment trzymający."""
        self._update_sim_torque({}, 0.0)

    async def _move_to(self, x: float, y: float, z: float, feed: float) -> None:
        """Ruch liniowy z interpolacją pozycji w czasie (feed w mm/min).

        Wszystkie ruchy symulatora przechodzą tędy, więc tu stosujemy limit
        prędkości z aktywnego profilu — jedno miejsce zamiast powtarzania
        przy każdym wywołaniu.
        """
        self._require_enable()
        sx, sy, sz = self.status.x, self.status.y, self.status.z
        dist = math.dist((sx, sy, sz), (x, y, z))
        if dist < 1e-9:
            self._settle_sim_torque()
            return
        moving = [
            axis
            for axis, delta in (("x", x - sx), ("y", y - sy), ("z", z - sz))
            if abs(delta) > 1e-9
        ]
        feed = self._capped_feed(feed, moving)
        deltas = {"x": x - sx, "y": y - sy, "z": z - sz}
        duration = dist / (feed / 60.0)
        steps = max(1, int(duration / 0.05))
        for i in range(1, steps + 1):
            self._require_enable()
            t = i / steps
            self.status.x = sx + (x - sx) * t
            self.status.y = sy + (y - sy) * t
            self.status.z = sz + (z - sz) * t
            # moment liczymy po przesunięciu pozycji — dodatek za skrawanie
            # zależy od bieżącej głębokości, nie od tej sprzed kroku
            self._update_sim_torque(deltas, feed)
            await asyncio.sleep(duration / steps)
        self._settle_sim_torque()


class SC4HubMachine(Machine):
    """Łącze TCP do mostka SC4-Hub (protokół tekstowy, port 8500).

    Serwer wysyła komendy wysokopoziomowe (HOME, MOVE, SPINDLE, STOP),
    a interpolację i obsługę serw ClearPath-SC wykonuje mostek `bridge/`
    (sFoundation, USB do SC4-Hub) — protokół opisuje `docs/ARCHITEKTURA.md`.
    Sygnał zezwolenia (Global Stop) czyta wyłącznie sprzęt i raportuje go
    w STATUS — z poziomu serwera jest tylko do odczytu.
    """

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._run_task: asyncio.Task | None = None
        # konfiguracja osi żyje w pamięci mostka — po każdym (ponownym)
        # połączeniu i po każdej zmianie trzeba ją wysłać jeszcze raz
        self._axes_pending = True

    def apply_axis_config(self, axes: dict[str, AxisConfig]) -> None:
        super().apply_axis_config(axes)
        self._axes_pending = True

    async def _push_axis_config(self) -> None:
        """Wysyła limity i przełożenia osi do mostka (wołane spod zamka).

        Tylko REQUIRED_AXES (X/Y/Z) — protokół mostka dziś nie zna innych
        liter osi. Ewentualne osie dodatkowe (podajnik, docisk) w
        `self.axes` czekają na rozszerzenie protokołu (temat C).
        """
        # znacznik kasujemy przed wysyłką: przy błędzie łącze i tak zostanie
        # zamknięte, a ponowne wejście tutaj dałoby pętlę
        self._axes_pending = False
        for axis in REQUIRED_AXES:
            cfg = self.axes.get(axis)
            if cfg is None:
                continue
            await self._exchange(
                f"AXCFG {axis.upper()} MMREV={cfg.mm_per_rev:.6f} "
                f"SOFTMIN={cfg.soft_min:.4f} SOFTMAX={cfg.soft_max:.4f} "
                f"LEN={cfg.length:.4f} HOME={cfg.home}"
            )

    async def _command(self, command: str) -> str:
        """Wysyła jedną komendę i zwraca linię odpowiedzi (OK ... / ERR ...)."""
        async with self._lock:
            # is_closing(): po restarcie sterownika gniazdo jest martwe, a samo
            # write() rzuciłoby wtedy RuntimeError zamiast błędu sieciowego
            if self._writer is None or self._writer.is_closing():
                self._reader = self._writer = None
                try:
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port), timeout=3.0
                    )
                except (OSError, asyncio.TimeoutError):
                    raise MachineError(
                        f"brak połączenia z mostkiem SC4-Hub "
                        f"({self.host}:{self.port})"
                    )
                # świeże połączenie może być połączeniem z nowo uruchomionym
                # mostkiem, który nie zna jeszcze limitów osi
                self._axes_pending = True
            if self._axes_pending:
                await self._push_axis_config()
            return await self._exchange(command)

    async def _exchange(self, command: str) -> str:
        """Jedna wymiana po otwartym już łączu — bez zamka i bez łączenia."""
        if self._writer is None or self._reader is None:
            raise MachineError("brak połączenia z mostkiem SC4-Hub")
        try:
            self._writer.write((command + "\n").encode())
            await self._writer.drain()
            line = await asyncio.wait_for(self._reader.readline(), timeout=30.0)
        except (OSError, asyncio.TimeoutError, RuntimeError):
            # RuntimeError: transport zamknięty pod spodem (uvloop)
            self._writer = None
            self._reader = None
            raise MachineError("utracono połączenie z mostkiem SC4-Hub")
        if not line:
            # koniec strumienia — bez tego pusta odpowiedź uchodziłaby za OK
            self._writer = None
            self._reader = None
            raise MachineError("mostek SC4-Hub zamknął połączenie")
        reply = line.decode().strip()
        if reply.startswith("ERR"):
            raise MachineError(f"mostek SC4-Hub odrzucił komendę: {reply}")
        return reply

    def _no_smart_in_bridge(self, what: str) -> MachineError:
        """Jeden komunikat na oba miejsca, w których SMART trafiłby do mostka.

        Świadomie **przerywamy pracę** zamiast wykonać zwykły ruch: krok SMART
        istnieje po to, żeby pilnować siły. Cichy przejazd bez tej kontroli
        wbiłby nóż w materiał z pełnym momentem — a operator zobaczyłby, że
        cykl „przeszedł".
        """
        return MachineError(
            f"{what}: mostek nie zna jeszcze komendy SMART (etap 5 tematu K) "
            "— na maszynie nie ma czym pilnować siły, więc nie wykonuję tego "
            "kroku jako zwykłego ruchu"
        )

    async def poll_status(self) -> None:
        """Cykliczne odpytywanie STATUS — wywoływane z pętli serwera."""
        reply = await self._command("STATUS")
        # przykład: OK STATE=READY EN=1 X=12.500 Y=-3.000 Z=10.000 SP=0 REL=- MSG=...
        # MSG jest ostatnie i zawiera spacje, więc odcinamy je przed rozbiciem
        msg = ""
        marker = reply.find(" MSG=")
        if marker >= 0:
            msg = reply[marker + 5:].strip()
            reply = reply[:marker]
        self.status.alarm_message = msg
        fields = dict(
            part.split("=", 1) for part in reply.split()[1:] if "=" in part
        )
        # Stany RUNNING i PAUSED wynikają z przebiegu programu, o którym wie
        # tylko serwer — sterownik między ruchami zgłasza READY. Gdyby STATUS
        # je nadpisywał, panel pokazywałby READY w trakcie cyklu, a wznowienie
        # po PAUZA przestałoby działać. ALARM ze sterownika ma pierwszeństwo
        # zawsze, bo oznacza realny problem na maszynie.
        if "STATE" in fields:
            reported = MachineState(fields["STATE"])
            server_driven = (MachineState.RUNNING, MachineState.PAUSED)
            if reported == MachineState.ALARM or self.status.state not in server_driven:
                self.status.state = reported
        self.status.safety_enable = fields.get("EN") == "1"
        self.status.x = float(fields.get("X", self.status.x))
        self.status.y = float(fields.get("Y", self.status.y))
        self.status.z = float(fields.get("Z", self.status.z))
        self.status.spindle_on = fields.get("SP") == "1"
        rel = fields.get("REL", "-")
        self.status.released_axes = [] if rel == "-" else sorted(c.lower() for c in rel)

        # Obciążenie osi: TRQX/TRQY/TRQZ w procentach momentu maksymalnego
        # (`sFnd::IMotion::TrqMeasured`, jednostka PCT_MAX — potwierdzone
        # w S-FoundationRef.chm). Mostek jeszcze tego nie wysyła; parser jest
        # gotowy, żeby po dopisaniu w C++ (etap 0 tematu K) panel dostał realny
        # pomiar bez zmiany w serwerze. Dopóki pól nie ma, źródłem jest "brak"
        # — pusty wskaźnik jest uczciwszy niż zera udające pomiar.
        measured = False
        for axis in ("x", "y", "z"):
            raw = fields.get("TRQ" + axis.upper())
            if raw is None:
                continue
            try:
                self.status.torque[axis] = float(raw)
            except ValueError:
                continue
            measured = True
        self.status.torque_source = "sterownik" if measured else "brak"

    async def home(self) -> None:
        self._require_not_released(["x", "y", "z"])
        await self._command("HOME")

    async def start(self) -> None:
        if self.status.state == MachineState.PAUSED:
            self.resume()
            return
        if not self._program:
            raise MachineError("nie załadowano programu — wybierz zlecenie w MES")
        self._require_not_released(["x", "y", "z"])
        if self.status.state != MachineState.READY:
            raise MachineError(
                f"start możliwy tylko w stanie READY (obecnie: {self.status.state.value})"
            )
        self.status.state = MachineState.RUNNING
        self.status.alarm_message = ""
        await self._start_spindle_with_machine()
        self._run_task = asyncio.create_task(self._run_program())

    async def stop(self) -> None:
        if self._run_task:
            self._run_task.cancel()
            self._run_task = None
        await self._command("STOP")

    async def reset(self) -> None:
        await self._command("RESET")
        self.status.current_op = None

    async def jog(self, axis: str, distance: float, feed: float) -> None:
        self._require_not_released([axis])
        # limit sprawdzamy także tutaj: mostek odrzuciłby ruch własnym błędem,
        # ale operator dostaje czytelniejszy komunikat i licznik pozycji
        # sterownika nie musi być pytany o zdanie przy każdym kliknięciu
        self._check_soft_limit(axis, getattr(self.status, axis) + distance)
        await self._command(f"JOG {axis.upper()} {distance:.3f} {feed:.0f}")

    async def set_released(self, axes: list[str], released: bool) -> None:
        cmd = "RELEASE" if released else "HOLD"
        if set(axes) == {"x", "y", "z"}:
            await self._command(f"{cmd} ALL")
        else:
            for axis in axes:
                await self._command(f"{cmd} {axis.upper()}")
        # natychmiastowe odbicie w statusie — bez czekania na kolejny STATUS
        await self.poll_status()

    async def _start_spindle_with_machine(self) -> None:
        """Wrzeciono rusza razem z maszyną, jeśli tak ustawiono (app/spindle.py).

        Obroty w komendzie są informacyjne — SC4-Hub ma tylko wyjście
        włącz/wyłącz, prędkość ustawia zewnętrzny regulator (temat J).
        """
        if self.spindle.start_with_machine:
            await self._command(f"SPINDLE 1 {self.spindle.default_rpm:.0f}")

    async def _run_program_operations(self, program: Program) -> None:
        """Tłumaczy operacje programu na sekwencję komend MOVE dla mostka.

        Wydzielone z `_run_program` (bez zmiany kolejności/treści komend —
        to jest ta sama sekwencja, która przeszła test na sprzęcie sesji
        2026-08-14), żeby krok PROGRAM cyklu maszyny mógł wywołać dokładnie
        to samo bez kończenia pracy maszyny (jak `_run_operations`
        w symulatorze).
        """
        zs = program.z_safe
        # Wrzeciono na starcie programu — konfigurowalne (app/spindle.py).
        # `spindle_running` pamięta, czy program je zapalił: po PAUZA wracamy
        # do tego stanu, zamiast zapalać je bezwarunkowo jak wcześniej.
        spindle_running = self.spindle.start_with_program
        if spindle_running:
            await self._command(f"SPINDLE 1 {program.spindle_rpm:.0f}")
        for op in program.operations:
            self.status.current_op = op.lp
            if op.op_type == "PAUZA":
                await self._command("SPINDLE 0")
                self.status.state = MachineState.PAUSED
                self._resume_event.clear()
                await self._resume_event.wait()
                self.status.state = MachineState.RUNNING
                if spindle_running:
                    await self._command(f"SPINDLE 1 {program.spindle_rpm:.0f}")
                continue
            if op.op_type == "SMART":
                raise self._no_smart_in_bridge(f"operacja LP={op.lp} (SMART)")
            if op.op_type == "WRZECIONO":
                if op.rpm > 0:
                    await self._command(f"SPINDLE 1 {op.rpm:.0f}")
                    spindle_running = True
                else:
                    await self._command("SPINDLE 0")
                    spindle_running = False
                continue

            if op.op_type == "SZYBKI":
                feed = op.feed or program.feed_travel
                await self._command(f"MOVEZ {zs:.3f} {program.feed_travel:.0f}")
                await self._command(f"MOVEXY {op.x:.3f} {op.y:.3f} {feed:.0f}")
                continue

            feed = op.feed or program.feed_work
            depths = pass_depths(op)
            path = cut_path(op)
            await self._command(f"MOVEZ {zs:.3f} {program.feed_travel:.0f}")
            await self._command(
                f"MOVEXY {op.x:.3f} {op.y:.3f} {program.feed_travel:.0f}"
            )
            for i, depth in enumerate(depths):
                await self._command(f"MOVEZ {depth:.3f} {feed:.0f}")
                for px, py in path:
                    await self._command(f"MOVEXY {px:.3f} {py:.3f} {feed:.0f}")
                await self._command(f"MOVEZ {zs:.3f} {program.feed_travel:.0f}")
                if path and i < len(depths) - 1:
                    await self._command(
                        f"MOVEXY {op.x:.3f} {op.y:.3f} {program.feed_travel:.0f}"
                    )
        await self._command(f"MOVEXY 0 0 {program.feed_travel:.0f}")
        # jak w symulatorze: granica programu detalu, nie koniec pracy maszyny
        if self.spindle.stop_after_program:
            await self._command("SPINDLE 0")

    async def _run_program(self) -> None:
        program = self._program
        assert program is not None
        try:
            await self._run_program_operations(program)
            self.status.current_op = None
            self.status.state = MachineState.READY
        except asyncio.CancelledError:
            raise
        except MachineError as exc:
            self.status.state = MachineState.ALARM
            self.status.alarm_message = str(exc)
        finally:
            try:
                await self._command("SPINDLE 0")
            except MachineError:
                pass
            self._run_task = None

    # --- cykl maszyny -------------------------------------------------
    #
    # UWAGA — napisane analogicznie do `_run_program_operations` (sprawdzonej
    # na sprzęcie), ale samo NIE BYŁO jeszcze uruchomione na fizycznej
    # maszynie — do zweryfikowania przy najbliższym uruchomieniu sprzętowym
    # (temat H). Pokryte testami z podstawionym `_command` (bez sprzętu),
    # patrz `docs/zmiany/cykl-na-sprzecie.md`.

    async def start_cycle(self, loop: bool = False) -> None:
        """Jak `SimulatedMachine.start_cycle` — te same reguły i komunikaty."""
        if self.status.state == MachineState.PAUSED:
            self.resume()
            return
        if self.status.state != MachineState.READY:
            raise MachineError(
                f"start cyklu możliwy tylko w stanie READY "
                f"(obecnie: {self.status.state.value})"
            )
        if not self.cycle.steps:
            raise MachineError("cykl maszyny nie jest zdefiniowany")
        if self.cycle.uses_program() and not self._program:
            raise MachineError(
                "cykl wywołuje program detalu, a żaden nie jest załadowany "
                "— wybierz zlecenie w MES"
            )
        self._require_not_released(["x", "y", "z"])
        self.status.state = MachineState.RUNNING
        self.status.alarm_message = ""
        self.status.cycle_loop = loop
        await self._start_spindle_with_machine()
        self._run_task = asyncio.create_task(self._run_cycle(loop))

    async def _run_cycle(self, loop: bool) -> None:
        try:
            while True:
                for step in self.cycle.steps:
                    self.status.cycle_step = step.lp
                    await self._execute_cycle_step(step)
                    await asyncio.sleep(0)  # patrz komentarz w SimulatedMachine
                self.status.cycle_step = None
                self.status.current_op = None
                if not loop:
                    break
            self.status.state = MachineState.READY
        except asyncio.CancelledError:
            raise
        except MachineError as exc:
            self.status.state = MachineState.ALARM
            self.status.alarm_message = str(exc)
        finally:
            try:
                await self._command("SPINDLE 0")
            except MachineError:
                pass
            self.status.cycle_loop = False
            self._run_task = None

    async def _execute_cycle_step(self, step: CycleStep) -> None:
        """Snapshot/restore profilu — jak w symulatorze, patrz tam po opis."""
        previous_profile = self.active_profile
        if step.profile and step.profile in self.profiles:
            self._set_profile(step.profile)
        try:
            await self._run_cycle_step_body(step)
        finally:
            self._set_profile(previous_profile)

    async def _run_cycle_step_body(self, step: CycleStep) -> None:
        if step.kind == STEP_PAUSE:
            await self._command("SPINDLE 0")
            self.status.state = MachineState.PAUSED
            self._resume_event.clear()
            await self._resume_event.wait()
            self.status.state = MachineState.RUNNING
            return

        if step.kind == STEP_OUTPUT:
            # Jak WYJSCIE w symulatorze: mostek nie ma jeszcze komendy
            # ustawienia wyjścia (etap 2b/3 tematu B) — stan widać na
            # ekranie, ale fizycznie nic się nie przełącza.
            self.status.outputs[step.output] = bool(step.output_on)
            return

        if step.kind == STEP_SMART:
            raise self._no_smart_in_bridge(f"krok {step.lp} (SMART)")

        if step.kind == STEP_PROGRAM:
            program = self._program
            if program is None:
                raise MachineError("krok PROGRAM: nie załadowano programu detalu")
            await self._run_program_operations(program)
            self.status.current_op = None
            return

        # STEP_MOVE — przejazd wskazanych osi; osie pominięte zostają na miejscu
        target = {"x": self.status.x, "y": self.status.y, "z": self.status.z}
        for axis, value in step.targets.items():
            if axis not in target:
                raise MachineError(
                    f"krok {step.lp}: oś {axis.upper()} nie jest obsługiwana "
                    "przez mostek (dziś tylko X/Y/Z)"
                )
            self._check_soft_limit(axis, value)
            target[axis] = value
        feed = step.feed or 1000.0
        await self._command(f"MOVEZ {target['z']:.3f} {feed:.0f}")
        await self._command(f"MOVEXY {target['x']:.3f} {target['y']:.3f} {feed:.0f}")


def create_machine(mode: str, host: str, port: int) -> Machine:
    """Warstwa maszyny wg trybu: "sc4hub" = sprzęt przez mostek, reszta = symulator.

    "clearcore" jest przyjmowane jako nazwa historyczna (patrz app/config.py) —
    tryb jest już znormalizowany przez konfigurację, ale sprawdzamy obie nazwy,
    żeby wywołanie `create_machine("clearcore", ...)` z testu albo skryptu
    nie uruchomiło po cichu symulatora na maszynie.
    """
    if mode in ("sc4hub", "clearcore"):
        return SC4HubMachine(host, port)
    return SimulatedMachine()
