"""Warstwa maszyny: wspólny interfejs, symulator oraz łącze do ClearCore.

Serwer rozmawia z maszyną wyłącznie przez klasę bazową Machine, więc panel,
API i integracja MES działają identycznie na symulatorze (MACHINE_MODE=sim)
i na sprzęcie (MACHINE_MODE=clearcore).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from enum import Enum

from .axes import AXIS_NAMES, AxisConfig
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
        }


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

    # --- konfiguracja osi (wspólna) ---------------------------------------

    def apply_axis_config(self, axes: dict[str, AxisConfig]) -> None:
        """Podmienia konfigurację osi; podklasy dosyłają ją do sprzętu."""
        self.axes = dict(axes)

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


class SimulatedMachine(Machine):
    """Symulator: ruchy w czasie rzeczywistym wg posuwów z programu.

    Pozwala rozwijać i testować panel, API oraz integrację MES bez sprzętu.
    Sygnał zezwolenia można przełączać z panelu (w trybie sprzętowym jest
    tylko do odczytu — pochodzi z wejścia ClearCore).
    """

    def __init__(self) -> None:
        super().__init__()
        self.status.state = MachineState.NOT_HOMED
        self.status.safety_enable = True  # symulacja: zezwolenie domyślnie aktywne
        self._run_task: asyncio.Task | None = None

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
        self._require_not_released(["x", "y", "z"])
        self._require_enable()
        self.status.state = MachineState.HOMING
        self._run_task = asyncio.create_task(self._do_home())

    async def _do_home(self) -> None:
        try:
            # symulacja bazowania: odjazd w górę i zjazd do punktu bazowego,
            # czyli do zera osi — odjazd ograniczony limitem programowym Z
            z_cfg = self.axes.get("z")
            lift = 40.0 if z_cfg is None else min(40.0, z_cfg.soft_max)
            await self._move_to(0.0, 0.0, lift, feed=2000)
            await self._move_to(0.0, 0.0, 0.0, feed=1000)
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
            for op in program.operations:
                self.status.current_op = op.lp
                await self._execute_operation(program, op)
            # koniec cyklu: odjazd na Z bezpieczne i powrót do bazy
            await self._move_to(self.status.x, self.status.y, program.z_safe, program.feed_travel)
            await self._move_to(0.0, 0.0, program.z_safe, program.feed_travel)
            self.status.current_op = None
            self.status.state = MachineState.READY
        except asyncio.CancelledError:
            raise
        except MachineError as exc:
            self._abort(str(exc))
        finally:
            self.status.spindle_on = False
            self._run_task = None

    async def _execute_operation(self, program: Program, op: Operation) -> None:
        if op.op_type == "PAUZA":
            self.status.spindle_on = False
            self.status.state = MachineState.PAUSED
            self._resume_event.clear()
            await self._resume_event.wait()
            self.status.state = MachineState.RUNNING
            return

        if op.op_type == "WRZECIONO":
            self.status.spindle_on = op.rpm > 0
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

        self.status.spindle_on = True
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

    async def _move_to(self, x: float, y: float, z: float, feed: float) -> None:
        """Ruch liniowy z interpolacją pozycji w czasie (feed w mm/min)."""
        self._require_enable()
        sx, sy, sz = self.status.x, self.status.y, self.status.z
        dist = math.dist((sx, sy, sz), (x, y, z))
        if dist < 1e-9:
            return
        duration = dist / (feed / 60.0)
        steps = max(1, int(duration / 0.05))
        for i in range(1, steps + 1):
            self._require_enable()
            t = i / steps
            self.status.x = sx + (x - sx) * t
            self.status.y = sy + (y - sy) * t
            self.status.z = sz + (z - sz) * t
            await asyncio.sleep(duration / steps)


class ClearCoreMachine(Machine):
    """Łącze TCP do sterownika ClearCore (protokół tekstowy, port 8500).

    Serwer wysyła komendy wysokopoziomowe (HOME, MOVE, SPINDLE, STOP),
    a interpolację i obsługę serw ClearPath wykonuje firmware
    (firmware/clearcore/). Sygnał zezwolenia jest czytany wyłącznie przez
    ClearCore z dedykowanego wejścia i raportowany w STATUS — z poziomu
    serwera jest tylko do odczytu.
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
        """Wysyła limity i przełożenia osi do mostka (wołane spod zamka)."""
        # znacznik kasujemy przed wysyłką: przy błędzie łącze i tak zostanie
        # zamknięte, a ponowne wejście tutaj dałoby pętlę
        self._axes_pending = False
        for axis in AXIS_NAMES:
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
                        f"brak połączenia ze sterownikiem ClearCore "
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
            raise MachineError("brak połączenia ze sterownikiem ClearCore")
        try:
            self._writer.write((command + "\n").encode())
            await self._writer.drain()
            line = await asyncio.wait_for(self._reader.readline(), timeout=30.0)
        except (OSError, asyncio.TimeoutError, RuntimeError):
            # RuntimeError: transport zamknięty pod spodem (uvloop)
            self._writer = None
            self._reader = None
            raise MachineError("utracono połączenie ze sterownikiem ClearCore")
        if not line:
            # koniec strumienia — bez tego pusta odpowiedź uchodziłaby za OK
            self._writer = None
            self._reader = None
            raise MachineError("sterownik zamknął połączenie")
        reply = line.decode().strip()
        if reply.startswith("ERR"):
            raise MachineError(f"sterownik odrzucił komendę: {reply}")
        return reply

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

    async def _run_program(self) -> None:
        """Tłumaczy operacje programu na sekwencję komend MOVE dla ClearCore."""
        program = self._program
        assert program is not None
        zs = program.z_safe
        try:
            await self._command(f"SPINDLE 1 {program.spindle_rpm:.0f}")
            for op in program.operations:
                self.status.current_op = op.lp
                if op.op_type == "PAUZA":
                    await self._command("SPINDLE 0")
                    self.status.state = MachineState.PAUSED
                    self._resume_event.clear()
                    await self._resume_event.wait()
                    self.status.state = MachineState.RUNNING
                    await self._command(f"SPINDLE 1 {program.spindle_rpm:.0f}")
                    continue
                if op.op_type == "WRZECIONO":
                    if op.rpm > 0:
                        await self._command(f"SPINDLE 1 {op.rpm:.0f}")
                    else:
                        await self._command("SPINDLE 0")
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


def create_machine(mode: str, host: str, port: int) -> Machine:
    if mode == "clearcore":
        return ClearCoreMachine(host, port)
    return SimulatedMachine()
