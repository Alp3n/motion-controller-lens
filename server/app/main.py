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

from . import axes, config, cycle, profiles
from .machine import (
    MachineError,
    MachineState,
    SC4HubMachine,
    SimulatedMachine,
    create_machine,
)
from .program import (
    NC12_RE,
    ProgramError,
    parse_program,
    validate_work_area,
)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """Uruchamia i zatrzymuje jedyny poller statusu sterownika."""
    task = None
    if isinstance(machine, SC4HubMachine):
        task = asyncio.create_task(_poll_loop())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Maszyna do odcinania wlewków — API", version="0.1.0", lifespan=lifespan
)

machine = create_machine(
    config.MACHINE_MODE, config.BRIDGE_HOST, config.BRIDGE_PORT
)

# Konfiguracja osi (długości, limity, przełożenia, punkty bazowania) — jedno
# źródło prawdy dla walidacji programów, ruchu ręcznego i mostka. Błędny plik
# przerywa start serwera; powód w app/axes.py.
axes_cfg = axes.load(config.AXES_FILE, config.WORK_AREA)
machine.apply_axis_config(axes_cfg)

# Profile parametrów ruchu (prędkości, rampy, limit momentu). Zakładane
# domyślnie dla osi z konfiguracji; błędny plik przerywa start tak samo jak
# błędna konfiguracja osi — powód w app/profiles.py.
profiles_cfg, active_profile = profiles.load(config.PROFILES_FILE, axes_cfg.keys())
machine.apply_profiles(profiles_cfg, active_profile)

# Cykl maszyny — kroki poziomu admina wokół programu detalu. Pusty, dopóki
# nie zostanie zdefiniowany; błędny plik przerywa start (powód w app/cycle.py).
cycle_cfg = cycle.load(config.CYCLE_FILE)
machine.apply_cycle(cycle_cfg)

STATIC_DIR = Path(__file__).parent / "static"

# Jeden poller na cały serwer. Wcześniej status odpytywała każda pętla
# WebSocketu z osobna: przy kilku otwartych panelach mnożyło to komendy do
# sterownika, uchwyty rywalizowały o wspólny zamek, a uchwyt zablokowany
# w odpytywaniu nie zauważał rozłączenia klienta i zostawał na zawsze.
# Przy okazji /api/status jest teraz aktualne także bez otwartego panelu.


async def _poll_loop() -> None:
    while True:
        with contextlib.suppress(MachineError):
            await machine.poll_status()
        await asyncio.sleep(0.2)


# --- modele żądań ---------------------------------------------------------


class SelectOrderRequest(BaseModel):
    """Wywoływane przez MES po wybraniu zlecenia przez operatora."""

    order_id: str = Field(..., description="numer zlecenia w MES")
    program_number: str = Field(..., description="12-cyfrowy numer programu (12 NC)")


class JogRequest(BaseModel):
    axis: str = Field(..., pattern="^[xyzXYZ]$")
    distance: float
    # brak wartości = użyj prędkości JOG skonfigurowanej dla osi (/axes)
    feed: float | None = None


class ReleaseRequest(BaseModel):
    """Luzowanie osi: pojedyncza oś albo 'all' (wszystkie na raz)."""

    axis: str = Field(..., pattern="^([xyzXYZ]|all|ALL)$")
    released: bool


class SaveProgramRequest(BaseModel):
    content: str = Field(..., description="pełna treść pliku .prg")


class SimEnableRequest(BaseModel):
    enabled: bool


class AxesRequest(BaseModel):
    """Konfiguracja osi z ekranu „Konfiguracja osi".

    Pola pojedynczej osi celowo nie są opisane modelem pydantica — walidacją
    zajmuje się app/axes.py, żeby operator zobaczył komunikat po polsku
    (długość, punkt bazowania, limity, przełożenie) zamiast błędu schematu.
    """

    axes: dict[str, dict] = Field(..., description="osie x, y, z")


class HomingRequest(BaseModel):
    """Konfiguracja bazowania z ekranu /homing.

    Celowo tylko pola bazowania — długości, limity i przełożenia zostają
    nietknięte, żeby pomyłka na tym ekranie nie skasowała limitów programowych
    (walidacja i scalanie: app/axes.py, `merge_homing`).
    """

    axes: dict[str, dict] = Field(..., description="oś -> pola bazowania")


class ProfilesRequest(BaseModel):
    """Profile parametrów ruchu z ekranu konfiguracji.

    Jak przy osiach — walidacją zajmuje się app/profiles.py, żeby operator
    zobaczył komunikat po polsku zamiast błędu schematu.
    """

    profiles: dict[str, dict] = Field(..., description="nazwa profilu -> osie")
    active: str = Field(..., description="nazwa profilu aktywnego")


class ActiveProfileRequest(BaseModel):
    active: str = Field(..., description="nazwa profilu do uaktywnienia")


class CycleRequest(BaseModel):
    """Definicja cyklu maszyny z ekranu admina.

    Jak przy osiach i profilach — walidacją zajmuje się app/cycle.py, żeby
    operator zobaczył komunikat po polsku z numerem kroku.
    """

    name: str = Field("", description="nazwa cyklu")
    steps: list[dict] = Field(..., description="kroki cyklu, LP ciągłe od 1")


class CycleStartRequest(BaseModel):
    """Uruchomienie cyklu — jeden przebieg (domyślnie) albo pętla (temat F)."""

    loop: bool = Field(False, description="tryb automatyczny — powtarzaj cykl bez zatrzymania")


# --- pomocnicze -----------------------------------------------------------


def _axis_warnings(current: dict) -> list[str]:
    """Ostrzeżenia o konfiguracji, która jest poprawna, ale kłopotliwa."""
    warnings = []
    for axis, cfg in current.items():
        if not (cfg.soft_min <= 0.0 <= cfg.soft_max):
            warnings.append(
                f"oś {axis.upper()}: punkt bazowania (zero osi) leży poza limitami "
                f"programowymi — po bazowaniu maszyna stanie poza dozwolonym zakresem"
            )
    program = machine.program
    if program is not None:
        try:
            validate_work_area(program, **axes.work_area(current))
        except ProgramError as exc:
            warnings.append(
                f"załadowany program {program.number} nie mieści się w tych "
                f"limitach: {exc}"
            )
    return warnings


def _profile_warnings(current: dict) -> list[str]:
    """Ostrzeżenia o profilach, które są poprawne, ale nie robią tego, co się wydaje."""
    warnings = []
    for name, absent in sorted(profiles.missing_axes(current, axes_cfg.keys()).items()):
        warnings.append(
            f"profil '{name}' nie opisuje osi "
            + ", ".join(a.upper() for a in absent)
            + " — te osie nie będą przez niego ograniczone"
        )
    # Limit momentu jest dziś parametrem wyłącznie po stronie serwera. Na
    # sprzęcie nie zadziała, dopóki protokół mostka nie dostanie komendy
    # momentu — a operator, który ustawia 10% „żeby było delikatnie", musi
    # wiedzieć, że na maszynie to nic nie zmienia.
    if config.MACHINE_MODE != "sim":
        warnings.append(
            "limit momentu nie jest wysyłany do sprzętu — protokół mostka nie ma "
            "jeszcze komendy momentu; wartość działa tylko w symulatorze"
        )
    return warnings


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
        validate_work_area(program, **axes.work_area(axes_cfg))
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
        validate_work_area(program, **axes.work_area(axes_cfg))
    except ProgramError as exc:
        raise HTTPException(422, str(exc))
    config.PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(req.content, encoding="utf-8")
    return {"ok": True, "number": number, "name": program.name}


# --- sterowanie maszyną ---------------------------------------------------


@app.get("/api/config")
async def get_config():
    """Parametry maszyny potrzebne panelowi (skalowanie podglądu, limity)."""
    return {
        # obszar roboczy = limity programowe osi z ekranu konfiguracji
        "work_area": axes.work_area(axes_cfg),
        "axes": axes.to_dict(axes_cfg),
        "jog_max_step": config.JOG_MAX_STEP,
        "machine_mode": config.MACHINE_MODE,
    }


# --- konfiguracja osi -----------------------------------------------------


@app.get("/api/axes")
async def get_axes():
    """Konfiguracja osi dla ekranu konfiguracji."""
    return {
        "axes": axes.to_dict(axes_cfg),
        "home_points": list(axes.HOME_POINTS),
        "home_modes": list(axes.HOME_MODES),
        "file": str(config.AXES_FILE),
        "warnings": _axis_warnings(axes_cfg),
    }


@app.put("/api/axes")
async def put_axes(req: AxesRequest):
    """Zapis konfiguracji osi: walidacja, plik, przekazanie do maszyny.

    Zmiana limitów w trakcie ruchu jest odrzucana — trwający cykl został
    zaplanowany pod poprzednie limity.
    """
    global axes_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(
            409, "nie można zmieniać konfiguracji osi w trakcie ruchu maszyny"
        )
    try:
        # pola, których ten ekran nie edytuje (bazowanie), biorą wartości
        # z obecnej konfiguracji — inaczej zapis skasowałby ustawienia /homing
        new_axes = axes.parse_axes(axes.with_current_values(req.axes, axes_cfg))
    except axes.AxisConfigError as exc:
        raise HTTPException(422, str(exc))

    warnings = _axis_warnings(new_axes)
    try:
        axes.save(config.AXES_FILE, new_axes)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.AXES_FILE}: {exc}")
    axes_cfg = new_axes
    machine.apply_axis_config(new_axes)
    return {"ok": True, "axes": axes.to_dict(new_axes), "warnings": warnings}


# --- bazowanie ------------------------------------------------------------


def _homing_payload(current: dict) -> dict:
    return {
        "axes": {
            name: {key: cfg.to_dict()[key] for key in axes.HOMING_FIELDS}
            for name, cfg in current.items()
        },
        "groups": axes.home_groups(current),
        "modes": list(axes.HOME_MODES),
        "required_axes": list(axes.REQUIRED_AXES),
        "file": str(config.AXES_FILE),
        "warnings": axes.homing_warnings(current, config.MACHINE_MODE != "sim"),
    }


@app.get("/api/homing")
async def get_homing():
    """Konfiguracja bazowania — kolejność, tryb, parametry dla ClearView."""
    return _homing_payload(axes_cfg)


@app.put("/api/homing")
async def put_homing(req: HomingRequest):
    """Zapis konfiguracji bazowania; reszta parametrów osi zostaje bez zmian."""
    global axes_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(
            409, "nie można zmieniać konfiguracji bazowania w trakcie ruchu maszyny"
        )
    try:
        new_axes = axes.merge_homing(axes_cfg, req.axes)
    except axes.AxisConfigError as exc:
        raise HTTPException(422, str(exc))
    try:
        axes.save(config.AXES_FILE, new_axes)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.AXES_FILE}: {exc}")
    axes_cfg = new_axes
    machine.apply_axis_config(new_axes)
    return {"ok": True, **_homing_payload(new_axes)}


# --- profile parametrów ruchu --------------------------------------------


@app.get("/api/profiles")
async def get_profiles():
    """Profile parametrów ruchu + który jest aktywny."""
    return {
        "profiles": profiles.to_dict(profiles_cfg),
        "active": machine.active_profile,
        "file": str(config.PROFILES_FILE),
        "warnings": _profile_warnings(profiles_cfg),
    }


@app.put("/api/profiles")
async def put_profiles(req: ProfilesRequest):
    """Zapis profili: walidacja, plik, przekazanie do maszyny."""
    global profiles_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(
            409, "nie można zmieniać profili w trakcie ruchu maszyny"
        )
    try:
        new_profiles, active = profiles.parse_profiles(
            {"profiles": req.profiles, "active": req.active}
        )
    except profiles.ProfileError as exc:
        raise HTTPException(422, str(exc))

    warnings = _profile_warnings(new_profiles)
    try:
        profiles.save(config.PROFILES_FILE, new_profiles, active)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.PROFILES_FILE}: {exc}")
    profiles_cfg = new_profiles
    machine.apply_profiles(new_profiles, active)
    return {
        "ok": True,
        "profiles": profiles.to_dict(new_profiles),
        "active": active,
        "warnings": warnings,
    }


@app.post("/api/profiles/active")
async def set_active_profile(req: ActiveProfileRequest):
    """Przełącza aktywny profil bez zmiany samych profili."""
    try:
        machine.set_active_profile(req.active)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    try:
        profiles.save(config.PROFILES_FILE, profiles_cfg, req.active)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.PROFILES_FILE}: {exc}")
    return {"ok": True, "active": machine.active_profile}


# --- cykl maszyny ---------------------------------------------------------


@app.get("/api/cycle")
async def get_cycle():
    """Definicja cyklu maszyny."""
    return {
        "cycle": cycle_cfg.to_dict(),
        "step_kinds": list(cycle.STEP_KINDS),
        "outputs": list(cycle.OUTPUT_NAMES),
        "file": str(config.CYCLE_FILE),
        "warnings": cycle.warnings(cycle_cfg, profiles_cfg.keys(), axes_cfg.keys()),
    }


@app.put("/api/cycle")
async def put_cycle(req: CycleRequest):
    """Zapis definicji cyklu: walidacja, plik, przekazanie do maszyny."""
    global cycle_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(409, "nie można zmieniać cyklu w trakcie ruchu maszyny")
    try:
        new_cycle = cycle.parse_cycle({"name": req.name, "steps": req.steps})
    except cycle.CycleError as exc:
        raise HTTPException(422, str(exc))

    result = cycle.warnings(new_cycle, profiles_cfg.keys(), axes_cfg.keys())
    try:
        cycle.save(config.CYCLE_FILE, new_cycle)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.CYCLE_FILE}: {exc}")
    cycle_cfg = new_cycle
    machine.apply_cycle(new_cycle)
    return {"ok": True, "cycle": new_cycle.to_dict(), "warnings": result}


@app.post("/api/machine/cycle/start")
async def start_cycle(req: CycleStartRequest | None = None):
    """Uruchamia cykl maszyny — jeden przebieg albo pętlę (tryb automatyczny),
    albo wznawia po PAUZA. Body opcjonalne — brak znaczy jeden przebieg,
    tak jak przed dodaniem trybu automatycznego (temat F).
    """
    loop = req.loop if req is not None else False
    try:
        await machine.start_cycle(loop=loop)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.get("/api/status")
async def get_status():
    return machine.status.to_dict()


@app.post("/api/machine/home")
async def machine_home():
    try:
        # home() waliduje synchronicznie i sam uruchamia ruch w tle;
        # create_task() w tym miejscu gubiło błędy walidacji (zawsze 200).
        await machine.home()
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
    axis = req.axis.lower()
    feed = req.feed if req.feed is not None else machine.axis_jog_feed(axis)
    try:
        await machine.jog(axis, distance, feed)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/release")
async def machine_release(req: ReleaseRequest):
    """Zdejmuje lub przywraca moment na osi — do ręcznego przestawiania.

    UWAGA: zluzowana oś nie stawia oporu. Oś pionowa bez hamulca opadnie
    pod własnym ciężarem.
    """
    try:
        axes = machine._parse_axes(req.axis)
        await machine.set_released(axes, req.released)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True, "released_axes": sorted(machine.status.released_axes)}


@app.post("/api/sim/safety-enable")
async def sim_safety_enable(req: SimEnableRequest):
    """Tylko symulator: przełączenie sygnału zezwolenia do testów.

    W trybie sprzętowym sygnał pochodzi z niezależnego systemu bezpieczeństwa
    (Global Stop na SC4-Hub) — nie da się go ustawić z oprogramowania.
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
            # sam wysyła — odpytywaniem sterownika zajmuje się _poll_loop()
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


@app.get("/axes", include_in_schema=False)
async def axes_page():
    return FileResponse(STATIC_DIR / "axes.html")


@app.get("/cycle", include_in_schema=False)
async def cycle_page():
    return FileResponse(STATIC_DIR / "cycle.html")


@app.get("/profiles", include_in_schema=False)
async def profiles_page():
    return FileResponse(STATIC_DIR / "profiles.html")


@app.get("/homing", include_in_schema=False)
async def homing_page():
    return FileResponse(STATIC_DIR / "homing.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
