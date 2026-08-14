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

from .program import Operation, Program


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
        }


class MachineError(Exception):
    """Błąd operacji maszynowej — komunikat po polsku dla operatora."""


class Machine:
    """Wspólny interfejs maszyny (symulator i sprzęt)."""

    def __init__(self) -> None:
        self.status = MachineStatus()
        self._program: Program | None = None
        self._resume_event = asyncio.Event()

    # --- ładowanie programu (wspólne) -------------------------------------

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
        if self.status.state in (MachineState.RUNNING, MachineState.HOMING):
            raise MachineError("maszyna jest w ruchu")
        self._require_enable()
        self.status.state = MachineState.HOMING
        try:
            # symulacja bazowania: zjazd do czujników krańcowych
            await self._move_to(0.0, 0.0, 40.0, feed=2000)
            await self._move_to(0.0, 0.0, 0.0, feed=1000)
        except asyncio.CancelledError:
            return
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

    async def jog(self, axis: str, distance: float, feed: float) -> None:
        if self.status.state not in (MachineState.READY, MachineState.NOT_HOMED):
            raise MachineError("JOG możliwy tylko przy zatrzymanej maszynie")
        self._require_enable()
        target = {
            "x": self.status.x,
            "y": self.status.y,
            "z": self.status.z,
        }
        if axis not in target:
            raise MachineError(f"nieznana oś: {axis}")
        target[axis] += distance
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

        self.status.spindle_on = True
        # dojazd nad punkt na wysokości bezpiecznej
        await self._move_to(self.status.x, self.status.y, program.z_safe, program.feed_travel)
        await self._move_to(op.x, op.y, program.z_safe, program.feed_travel)
        # zagłębienie posuwem roboczym
        await self._move_to(op.x, op.y, op.z, program.feed_work)
        if op.op_type == "LINIA":
            await self._move_to(op.x2, op.y2, op.z, program.feed_work)
        # wycofanie
        await self._move_to(self.status.x, self.status.y, program.z_safe, program.feed_travel)

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

    async def _command(self, command: str) -> str:
        """Wysyła jedną komendę i zwraca linię odpowiedzi (OK ... / ERR ...)."""
        async with self._lock:
            if self._writer is None:
                try:
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port), timeout=3.0
                    )
                except (OSError, asyncio.TimeoutError):
                    raise MachineError(
                        f"brak połączenia ze sterownikiem ClearCore "
                        f"({self.host}:{self.port})"
                    )
            try:
                self._writer.write((command + "\n").encode())
                await self._writer.drain()
                line = await asyncio.wait_for(self._reader.readline(), timeout=30.0)
            except (OSError, asyncio.TimeoutError):
                self._writer = None
                self._reader = None
                raise MachineError("utracono połączenie ze sterownikiem ClearCore")
            reply = line.decode().strip()
            if reply.startswith("ERR"):
                raise MachineError(f"sterownik odrzucił komendę: {reply}")
            return reply

    async def poll_status(self) -> None:
        """Cykliczne odpytywanie STATUS — wywoływane z pętli serwera."""
        reply = await self._command("STATUS")
        # przykład: OK STATE=READY EN=1 X=12.500 Y=-3.000 Z=10.000 SP=0
        fields = dict(
            part.split("=", 1) for part in reply.split()[1:] if "=" in part
        )
        if "STATE" in fields:
            self.status.state = MachineState(fields["STATE"])
        self.status.safety_enable = fields.get("EN") == "1"
        self.status.x = float(fields.get("X", self.status.x))
        self.status.y = float(fields.get("Y", self.status.y))
        self.status.z = float(fields.get("Z", self.status.z))
        self.status.spindle_on = fields.get("SP") == "1"

    async def home(self) -> None:
        await self._command("HOME")

    async def start(self) -> None:
        if self.status.state == MachineState.PAUSED:
            self.resume()
            return
        if not self._program:
            raise MachineError("nie załadowano programu — wybierz zlecenie w MES")
        if self.status.state != MachineState.READY:
            raise MachineError(
                f"start możliwy tylko w stanie READY (obecnie: {self.status.state.value})"
            )
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
        await self._command(f"JOG {axis.upper()} {distance:.3f} {feed:.0f}")

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
                    await self._command(f"SPINDLE 1 {program.spindle_rpm:.0f}")
                    continue
                await self._command(f"MOVEZ {zs:.3f} {program.feed_travel:.0f}")
                await self._command(
                    f"MOVEXY {op.x:.3f} {op.y:.3f} {program.feed_travel:.0f}"
                )
                await self._command(f"MOVEZ {op.z:.3f} {program.feed_work:.0f}")
                if op.op_type == "LINIA":
                    await self._command(
                        f"MOVEXY {op.x2:.3f} {op.y2:.3f} {program.feed_work:.0f}"
                    )
                await self._command(f"MOVEZ {zs:.3f} {program.feed_travel:.0f}")
            await self._command(f"MOVEXY 0 0 {program.feed_travel:.0f}")
            self.status.current_op = None
        except asyncio.CancelledError:
            raise
        except MachineError as exc:
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
