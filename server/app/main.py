"""Serwer maszyny — API REST (MES, programy, sterowanie) + panel WWW.

Uruchomienie (z katalogu server/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .machine import (
    ClearCoreMachine,
    MachineError,
    SimulatedMachine,
    create_machine,
)
from .program import (
    NC12_RE,
    ProgramError,
    parse_program,
    validate_work_area,
)

app = FastAPI(title="Maszyna do ocinania wlewków — API", version="0.1.0")

machine = create_machine(
    config.MACHINE_MODE, config.CLEARCORE_HOST, config.CLEARCORE_PORT
)

STATIC_DIR = Path(__file__).parent / "static"


# --- modele żądań ---------------------------------------------------------


class SelectOrderRequest(BaseModel):
    """Wywoływane przez MES po wybraniu zlecenia przez operatora."""

    order_id: str = Field(..., description="numer zlecenia w MES")
    program_number: str = Field(..., description="12-cyfrowy numer programu (12 NC)")


class JogRequest(BaseModel):
    axis: str = Field(..., pattern="^[xyzXYZ]$")
    distance: float
    feed: float = 500.0


class SaveProgramRequest(BaseModel):
    content: str = Field(..., description="pełna treść pliku .prg")


class SimEnableRequest(BaseModel):
    enabled: bool


# --- pomocnicze -----------------------------------------------------------


def _program_path(number: str) -> Path:
    if not NC12_RE.match(number):
        raise HTTPException(400, "numer programu musi mieć dokładnie 12 cyfr")
    return config.PROGRAMS_DIR / f"{number}.prg"


def _load_and_validate(number: str):
    path = _program_path(number)
    if not path.exists():
        raise HTTPException(404, f"brak pliku programu {number}.prg w katalogu programów")
    try:
        program = parse_program(path.read_text(encoding="utf-8"), expected_number=number)
        validate_work_area(program, **config.WORK_AREA)
    except ProgramError as exc:
        raise HTTPException(422, f"błąd w programie {number}: {exc}")
    return program


# --- MES ------------------------------------------------------------------


@app.post("/api/mes/select-order")
async def mes_select_order(req: SelectOrderRequest):
    """MES podaje zlecenie i numer programu; maszyna ładuje konfigurację."""
    program = _load_and_validate(req.program_number)
    try:
        machine.load_program(program, req.order_id)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {
        "ok": True,
        "order_id": req.order_id,
        "program": program.to_dict(),
    }


# --- programy (edytor technologa) ----------------------------------------


@app.get("/api/programs")
async def list_programs():
    """Lista programów w katalogu — numer + nazwa (jeśli plik poprawny)."""
    items = []
    for path in sorted(config.PROGRAMS_DIR.glob("*.prg")):
        number = path.stem
        if not NC12_RE.match(number):
            continue
        entry = {"number": number, "name": "", "valid": True, "error": ""}
        try:
            program = parse_program(path.read_text(encoding="utf-8"), expected_number=number)
            entry["name"] = program.name
        except ProgramError as exc:
            entry["valid"] = False
            entry["error"] = str(exc)
        items.append(entry)
    return {"programs": items}


@app.get("/api/programs/{number}")
async def get_program(number: str):
    """Program w postaci strukturalnej (dla edytora) + surowa treść pliku."""
    path = _program_path(number)
    if not path.exists():
        raise HTTPException(404, f"brak pliku programu {number}.prg")
    text = path.read_text(encoding="utf-8")
    result: dict = {"number": number, "content": text, "parsed": None, "error": ""}
    try:
        result["parsed"] = parse_program(text, expected_number=number).to_dict()
    except ProgramError as exc:
        result["error"] = str(exc)
    return result


@app.get("/api/programs/{number}/raw", response_class=PlainTextResponse)
async def get_program_raw(number: str):
    """Surowy plik .prg — do pobrania/edycji w Excelu."""
    path = _program_path(number)
    if not path.exists():
        raise HTTPException(404, f"brak pliku programu {number}.prg")
    return path.read_text(encoding="utf-8")


@app.put("/api/programs/{number}")
async def save_program(number: str, req: SaveProgramRequest):
    """Zapis programu przez technologa — plik jest walidowany przed zapisem."""
    path = _program_path(number)
    try:
        program = parse_program(req.content, expected_number=number)
        validate_work_area(program, **config.WORK_AREA)
    except ProgramError as exc:
        raise HTTPException(422, str(exc))
    config.PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(req.content, encoding="utf-8")
    return {"ok": True, "number": number, "name": program.name}


# --- sterowanie maszyną ---------------------------------------------------


@app.get("/api/status")
async def get_status():
    return machine.status.to_dict()


@app.post("/api/machine/home")
async def machine_home():
    try:
        asyncio.create_task(machine.home())
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/start")
async def machine_start():
    try:
        await machine.start()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/stop")
async def machine_stop():
    await machine.stop()
    return {"ok": True}


@app.post("/api/machine/reset")
async def machine_reset():
    await machine.reset()
    return {"ok": True}


@app.post("/api/machine/jog")
async def machine_jog(req: JogRequest):
    distance = max(-config.JOG_MAX_STEP, min(config.JOG_MAX_STEP, req.distance))
    try:
        await machine.jog(req.axis.lower(), distance, req.feed)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/sim/safety-enable")
async def sim_safety_enable(req: SimEnableRequest):
    """Tylko symulator: przełączenie sygnału zezwolenia do testów.

    W trybie sprzętowym sygnał pochodzi z niezależnego systemu bezpieczeństwa
    i jest czytany przez ClearCore — nie da się go ustawić z oprogramowania.
    """
    if not isinstance(machine, SimulatedMachine):
        raise HTTPException(409, "dostępne tylko w trybie symulacji (MACHINE_MODE=sim)")
    machine.set_safety_enable(req.enabled)
    return {"ok": True, "safety_enable": req.enabled}


# --- status na żywo (WebSocket) ------------------------------------------


@app.websocket("/ws/status")
async def ws_status(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            if isinstance(machine, ClearCoreMachine):
                with contextlib.suppress(MachineError):
                    await machine.poll_status()
            await ws.send_json(machine.status.to_dict())
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass


# --- panel WWW ------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/editor", include_in_schema=False)
async def editor():
    return FileResponse(STATIC_DIR / "editor.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
