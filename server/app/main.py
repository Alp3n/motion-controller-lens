"""Serwer maszyny — API REST (MES, programy, sterowanie) + panel WWW.

Uruchomienie (z katalogu server/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audit, axes, config, cycle, kalibracja, outputs, profiles, smart, spindle, users
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
    smart_warnings,
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

# Definicje SMART — nazwane zestawy parametrów procedur sterowanych siłą,
# wspólne dla programu technologa i cyklu maszyny. Błędny plik przerywa start,
# jak przy osiach i profilach: te wartości decydują o sile dociskanej do
# materiału (powód w app/smart.py). Wczytywane PRZED cyklem, bo kroki cyklu
# odwołują się do definicji po nazwie.
smart_cfg = smart.load(config.SMART_FILE)
machine.apply_smart(smart_cfg)

# Kalibracja moment -> siła (etap 2 tematu K) — pary (moment %, siła N)
# wpisane po pomiarze siłomierzem. Dane pomocnicze do dobierania progów,
# nie parametr bezpieczeństwa: błędny/brakujący plik nie przerywa startu
# (powód w app/kalibracja.py).
kalibracja_cfg = kalibracja.load(config.KALIBRACJA_FILE)

# Cykl maszyny — kroki poziomu admina wokół programu detalu. Pusty, dopóki
# nie zostanie zdefiniowany; błędny plik przerywa start (powód w app/cycle.py).
cycle_cfg = cycle.load(config.CYCLE_FILE)
machine.apply_cycle(cycle_cfg)

# Wyjścia cyfrowe (BRAKE_0/BRAKE_1) — do czego służą i co się z nimi dzieje
# przy STOP. Błędny plik przerywa start; powód w app/outputs.py.
outputs_cfg = outputs.load(config.OUTPUTS_FILE)
machine.apply_output_config(outputs_cfg)

# Wrzeciono — kiedy się załącza i kiedy gaśnie. Błędny plik przerywa start
# tak samo jak reszta konfiguracji; powód w app/spindle.py.
spindle_cfg = spindle.load(config.SPINDLE_FILE)
machine.apply_spindle_config(spindle_cfg)

# Konta i sesje. Pusty słownik kont = logowanie wyłączone (patrz app/users.py):
# maszyna, która dziś pracuje bez logowania, nie może po aktualizacji serwera
# zostać zablokowana przed operatorem. Błędny plik przerywa start.
users_cfg = users.load(config.USERS_FILE)
sessions = users.Sessions(config.SESSION_TTL)

STATIC_DIR = Path(__file__).parent / "static"


# --- logowanie i role -----------------------------------------------------


def auth_enabled() -> bool:
    """Logowanie działa dopiero, gdy istnieje choć jedno konto."""
    return bool(users_cfg)


def _user_from_request(request: Request) -> users.User | None:
    login = sessions.login_for(request.cookies.get(users.COOKIE_NAME))
    if login is None:
        return None
    return users_cfg.get(login)


def current_user(request: Request) -> users.User | None:
    """Zalogowany użytkownik albo None (także gdy logowanie jest wyłączone)."""
    return _user_from_request(request)


def require_role(required: str):
    """Zależność FastAPI: wpuszcza rolę `required` i wyższe.

    Przy wyłączonym logowaniu przepuszcza wszystko — inaczej aktualizacja
    serwera odcięłaby panel na maszynie, która nie ma jeszcze założonych kont.
    """

    def dependency(request: Request) -> users.User | None:
        if not auth_enabled():
            return None
        user = _user_from_request(request)
        if user is None:
            raise HTTPException(401, "zaloguj się, żeby wykonać tę operację")
        if not users.role_allows(user.role, required):
            raise HTTPException(
                403,
                f"rola „{user.role}” nie ma uprawnień do tej operacji "
                f"(wymagana: {required} lub wyższa)",
            )
        return user

    return dependency


require_operator = require_role(users.ROLE_OPERATOR)
require_technolog = require_role(users.ROLE_TECHNOLOG)
require_admin = require_role(users.ROLE_ADMIN)


def require_mes_token(request: Request) -> None:
    """Token integracji MES — osobny kanał od ról operatora (wywołuje to
    system, nie człowiek, więc nie ma tu sesji/ciasteczka do sprawdzenia).

    Bez ustawionego `MES_TOKEN` endpoint zostaje otwarty jak dotychczas —
    to świadomie zachowana kompatybilność (temat E), nie przeoczenie: MES,
    który dziś nie ma czym się przedstawić, nie może stracić integracji po
    aktualizacji serwera.
    """
    token = config.MES_TOKEN
    if not token:
        return
    got = request.headers.get("X-MES-Token", "")
    if not secrets.compare_digest(got, token):
        raise HTTPException(401, "nieprawidłowy lub brakujący token MES (nagłówek X-MES-Token)")


def _log(user: users.User | None, action: str, detail: str = "") -> None:
    """Wpis do dziennika zmian; bez logowania zapisujemy to wprost."""
    audit.record(
        config.AUDIT_FILE,
        login=user.login if user else "(bez logowania)",
        role=user.role if user else "-",
        action=action,
        detail=detail,
    )


def _page(request: Request, filename: str, required: str) -> Response:
    """Strona panelu chroniona rolą — bez uprawnień odsyła na ekran logowania.

    Przekierowanie zamiast 403, bo to jest wejście z paska adresu albo
    z odnośnika: operator ma zobaczyć formularz logowania, nie surowy błąd.
    """
    if auth_enabled():
        user = _user_from_request(request)
        if user is None:
            return RedirectResponse(f"/login?cel={request.url.path}", status_code=303)
        if not users.role_allows(user.role, required):
            return FileResponse(STATIC_DIR / "brak-dostepu.html", status_code=403)
    return FileResponse(STATIC_DIR / filename)

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


class LoginRequest(BaseModel):
    login: str = Field(..., max_length=64)
    password: str = Field(..., max_length=256)


class OutputsRequest(BaseModel):
    """Przeznaczenie wyjść cyfrowych z ekranu cyklu maszyny.

    Jak przy osiach i profilach — walidacją zajmuje się app/outputs.py, żeby
    admin zobaczył komunikat po polsku zamiast błędu schematu.
    """

    outputs: dict[str, dict] = Field(..., description="wyjscie_0 / wyjscie_1")


class SpindleRequest(BaseModel):
    """Ustawienia wrzeciona — zapis częściowy.

    Panel operatora wysyła sam przełącznik „przy starcie maszyny", ekran cyklu
    tylko opcje granic programu; brakujące pola zostają bez zmian
    (`SpindleConfig.merged` w app/spindle.py).
    """

    start_with_machine: bool | None = None
    start_with_program: bool | None = None
    stop_after_program: bool | None = None
    default_rpm: float | None = None


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


class SmartRequest(BaseModel):
    """Definicje SMART z ekranu /smart.

    Jak przy osiach, profilach i cyklu — walidacją zajmuje się app/smart.py,
    żeby operator zobaczył komunikat po polsku z nazwą definicji i parametru.
    """

    definitions: dict[str, dict] = Field(
        ..., description="nazwa definicji -> {procedure, params, note}"
    )


class KalibracjaRequest(BaseModel):
    """Punkty kalibracji moment -> siła z ekranu `/sila`.

    Jak przy osiach, profilach i SMART — walidacją zajmuje się
    app/kalibracja.py, żeby operator zobaczył komunikat po polsku.
    """

    kalibracja: dict[str, dict] = Field(
        ..., description="oś (x/y/z) -> {punkty: [{moment_pct, sila_n, ...}]}"
    )


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


# --- logowanie ------------------------------------------------------------


@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Kto jest zalogowany i czy logowanie w ogóle działa.

    Panel pyta o to przy każdym otwarciu ekranu — stąd wie, które odnośniki
    pokazać i czy w nagłówku ma być przycisk „Wyloguj".
    """
    user = current_user(request)
    return {
        "auth_enabled": auth_enabled(),
        "user": user.public() if user else None,
        "roles": list(users.ROLES),
    }


@app.post("/api/auth/login")
async def auth_login(req: LoginRequest, response: Response):
    """Logowanie loginem i hasłem.

    Komunikat błędu jest celowo jednakowy dla nieznanego loginu i złego hasła —
    inaczej formularz podpowiadałby, które konta istnieją.
    """
    if not auth_enabled():
        raise HTTPException(
            409,
            "logowanie jest wyłączone — na tym serwerze nie założono jeszcze "
            "żadnego konta (tools/konta.py)",
        )
    login = req.login.strip().lower()
    locked = sessions.locked_for(login)
    if locked > 0:
        _log(None, "logowanie zablokowane", f"login {login}")
        raise HTTPException(
            429,
            f"za dużo nieudanych prób — spróbuj ponownie za {int(locked / 60) + 1} min",
        )
    user = users_cfg.get(login)
    if user is None or not users.verify_password(req.password, user.password_hash):
        sessions.note_failure(login)
        _log(None, "nieudane logowanie", f"login {login}")
        raise HTTPException(401, "nieprawidłowy login albo hasło")

    sessions.note_success(login)
    token = sessions.create(login)
    # Bez `secure`: panel na hali chodzi po zwykłym HTTP i ciasteczko z flagą
    # secure nigdy by nie doszło. Konsekwencje opisane w app/users.py.
    response.set_cookie(
        users.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=int(config.SESSION_TTL),
        path="/",
    )
    _log(user, "zalogowanie")
    return {"ok": True, "user": user.public()}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    user = current_user(request)
    sessions.drop(request.cookies.get(users.COOKIE_NAME))
    response.delete_cookie(users.COOKIE_NAME, path="/")
    if user:
        _log(user, "wylogowanie")
    return {"ok": True}


# --- MES ------------------------------------------------------------------


@app.post("/api/mes/select-order")
async def mes_select_order(req: SelectOrderRequest, _token=Depends(require_mes_token)):
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
async def list_programs(user=Depends(require_technolog)):
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
async def get_program(number: str, user=Depends(require_technolog)):
    """Program w postaci strukturalnej (dla edytora) + surowa treść pliku."""
    path = _program_path(number)
    if not path.exists():
        raise HTTPException(404, f"brak pliku programu {number}.prg")
    text = path.read_text(encoding="utf-8")
    result: dict = {
        "number": number, "content": text, "parsed": None, "error": "", "warnings": [],
    }
    try:
        program = parse_program(text, expected_number=number)
        result["parsed"] = program.to_dict()
        result["warnings"] = smart_warnings(program, smart_cfg.keys())
    except ProgramError as exc:
        result["error"] = str(exc)
    return result


@app.get("/api/programs/{number}/raw", response_class=PlainTextResponse)
async def get_program_raw(number: str, user=Depends(require_technolog)):
    """Surowy plik .prg — do pobrania/edycji w Excelu."""
    path = _program_path(number)
    if not path.exists():
        raise HTTPException(404, f"brak pliku programu {number}.prg")
    return path.read_text(encoding="utf-8")


@app.put("/api/programs/{number}")
async def save_program(
    number: str, req: SaveProgramRequest, user=Depends(require_technolog)
):
    """Zapis programu przez technologa — plik jest walidowany przed zapisem."""
    path = _program_path(number)
    try:
        program = parse_program(req.content, expected_number=number)
        validate_work_area(program, **axes.work_area(axes_cfg))
    except ProgramError as exc:
        raise HTTPException(422, str(exc))
    config.PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(req.content, encoding="utf-8")
    _log(user, "zapis programu technologa", f"{number} ({program.name})")
    return {
        "ok": True,
        "number": number,
        "name": program.name,
        # brakująca definicja SMART nie blokuje zapisu (plik .prg jest
        # samodzielny), ale technolog musi ją zobaczyć od razu, a nie dopiero
        # przy starcie na maszynie
        "warnings": smart_warnings(program, smart_cfg.keys()),
    }


# --- sterowanie maszyną ---------------------------------------------------


@app.get("/api/config")
async def get_config(user=Depends(require_operator)):
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
async def get_axes(user=Depends(require_operator)):
    """Konfiguracja osi dla ekranu konfiguracji."""
    return {
        "axes": axes.to_dict(axes_cfg),
        "home_points": list(axes.HOME_POINTS),
        "home_modes": list(axes.HOME_MODES),
        "file": str(config.AXES_FILE),
        "warnings": _axis_warnings(axes_cfg),
    }


@app.put("/api/axes")
async def put_axes(req: AxesRequest, user=Depends(require_admin)):
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
    _log(user, "zapis konfiguracji osi", ", ".join(sorted(new_axes)).upper())
    return {"ok": True, "axes": axes.to_dict(new_axes), "warnings": warnings}


# --- wyjścia cyfrowe ------------------------------------------------------


def _outputs_payload(current: dict) -> dict:
    return {
        "outputs": outputs.to_dict(current),
        "purposes": list(outputs.PURPOSES),
        # które wyjście zabiera wrzeciono — ekran ma to pokazać, zanim ktoś
        # zdefiniuje na nim podajnik i zdziwi się odmową sterownika
        "spindle_output": outputs.spindle_output_name(config.SPINDLE_OUTPUT),
        "file": str(config.OUTPUTS_FILE),
        "warnings": outputs.warnings(
            current,
            cycle.outputs_used(cycle_cfg),
            config.MACHINE_MODE != "sim",
            config.SPINDLE_OUTPUT,
        ),
    }


@app.get("/api/outputs")
async def get_outputs(user=Depends(require_operator)):
    """Przeznaczenie wyjść cyfrowych — etykiety dla panelu i ekranu cyklu."""
    return _outputs_payload(outputs_cfg)


@app.put("/api/outputs")
async def put_outputs(req: OutputsRequest, user=Depends(require_admin)):
    """Zapis przeznaczenia wyjść.

    Odrzucamy w ruchu z tego samego powodu co resztę konfiguracji: trwający
    cykl przełącza właśnie te wyjścia.
    """
    global outputs_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(
            409, "nie można zmieniać konfiguracji wyjść w trakcie ruchu maszyny"
        )
    try:
        new_cfg = outputs.parse_outputs(req.outputs)
    except outputs.OutputConfigError as exc:
        raise HTTPException(422, str(exc))
    try:
        outputs.save(config.OUTPUTS_FILE, new_cfg)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.OUTPUTS_FILE}: {exc}")
    outputs_cfg = new_cfg
    machine.apply_output_config(new_cfg)
    _log(
        user,
        "zapis przeznaczenia wyjść",
        ", ".join(f"{n}={c.purpose}" for n, c in sorted(new_cfg.items())),
    )
    return {"ok": True, **_outputs_payload(new_cfg)}


# --- wrzeciono ------------------------------------------------------------


def _spindle_payload(cfg) -> dict:
    return {
        "spindle": cfg.to_dict(),
        "file": str(config.SPINDLE_FILE),
        "warnings": spindle.warnings(
            cfg, config.MACHINE_MODE != "sim", config.SPINDLE_OUTPUT
        ),
    }


@app.get("/api/spindle")
async def get_spindle(user=Depends(require_operator)):
    """Konfiguracja wrzeciona: kiedy się załącza i kiedy gaśnie."""
    return _spindle_payload(spindle_cfg)


@app.put("/api/spindle")
async def put_spindle(req: SpindleRequest, user=Depends(require_admin)):
    """Zapis ustawień wrzeciona; pominięte pola zostają bez zmian.

    Zmiana w trakcie ruchu jest odrzucana — przełączenie „wrzeciono rusza
    z maszyną" w środku cyklu i tak nie zadziałałoby wstecz, a sugerowałoby,
    że coś się zmieniło.
    """
    global spindle_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(
            409, "nie można zmieniać ustawień wrzeciona w trakcie ruchu maszyny"
        )
    changes = {k: v for k, v in req.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(422, "nie podano żadnego ustawienia do zmiany")
    try:
        new_cfg = spindle_cfg.merged(changes)
    except spindle.SpindleConfigError as exc:
        raise HTTPException(422, str(exc))
    try:
        spindle.save(config.SPINDLE_FILE, new_cfg)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.SPINDLE_FILE}: {exc}")
    spindle_cfg = new_cfg
    machine.apply_spindle_config(new_cfg)
    _log(user, "zapis ustawień wrzeciona", ", ".join(f"{k}={v}" for k, v in changes.items()))
    return {"ok": True, **_spindle_payload(new_cfg)}


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
async def get_homing(user=Depends(require_operator)):
    """Konfiguracja bazowania — kolejność, tryb, parametry dla ClearView."""
    return _homing_payload(axes_cfg)


@app.put("/api/homing")
async def put_homing(req: HomingRequest, user=Depends(require_admin)):
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
    _log(user, "zapis konfiguracji bazowania", ", ".join(sorted(req.axes)).upper())
    return {"ok": True, **_homing_payload(new_axes)}


# --- profile parametrów ruchu --------------------------------------------


@app.get("/api/profiles")
async def get_profiles(user=Depends(require_operator)):
    """Profile parametrów ruchu + który jest aktywny."""
    return {
        "profiles": profiles.to_dict(profiles_cfg),
        "active": machine.active_profile,
        "file": str(config.PROFILES_FILE),
        "warnings": _profile_warnings(profiles_cfg),
    }


@app.put("/api/profiles")
async def put_profiles(req: ProfilesRequest, user=Depends(require_admin)):
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
    _log(user, "zapis profili parametrów ruchu", f"aktywny: {active}")
    return {
        "ok": True,
        "profiles": profiles.to_dict(new_profiles),
        "active": active,
        "warnings": warnings,
    }


@app.post("/api/profiles/active")
async def set_active_profile(
    req: ActiveProfileRequest, user=Depends(require_admin)
):
    """Przełącza aktywny profil bez zmiany samych profili."""
    try:
        machine.set_active_profile(req.active)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    try:
        profiles.save(config.PROFILES_FILE, profiles_cfg, req.active)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.PROFILES_FILE}: {exc}")
    _log(user, "zmiana aktywnego profilu", machine.active_profile)
    return {"ok": True, "active": machine.active_profile}


# --- definicje SMART ------------------------------------------------------


@app.get("/api/smart")
async def get_smart(user=Depends(require_operator)):
    """Definicje SMART + rejestr procedur (żeby ekran wiedział, co narysować)."""
    return {
        "definitions": smart.to_dict(smart_cfg),
        "procedures": smart.procedures_to_dict(),
        "file": str(config.SMART_FILE),
        "warnings": smart.warnings(smart_cfg, config.MACHINE_MODE),
    }


@app.put("/api/smart")
async def put_smart(req: SmartRequest, user=Depends(require_admin)):
    """Zapis definicji SMART: walidacja, plik.

    Zapis odrzucamy w ruchu z tego samego powodu co profile — definicja może
    być właśnie używana przez wykonywany krok cyklu.
    """
    global smart_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(
            409, "nie można zmieniać definicji SMART w trakcie ruchu maszyny"
        )
    try:
        new_defs = smart.parse_definitions({"definitions": req.definitions})
    except smart.SmartError as exc:
        raise HTTPException(422, str(exc))

    try:
        smart.save(config.SMART_FILE, new_defs)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.SMART_FILE}: {exc}")
    smart_cfg = new_defs
    machine.apply_smart(new_defs)
    # SMART to ruch z kontrolą siły — zmiana tych liczb zmienia, jak mocno
    # maszyna naciska na detal. Dokładnie po to jest dziennik zmian.
    _log(user, "zapis definicji SMART", ", ".join(sorted(new_defs)))
    return {
        "ok": True,
        "definitions": smart.to_dict(new_defs),
        # ostrzeżenia o cyklu też, bo zmiana nazwy definicji może osierocić
        # krok SMART, a admin zobaczyłby to dopiero przy starcie cyklu
        "warnings": smart.warnings(new_defs, config.MACHINE_MODE)
        + cycle.warnings(cycle_cfg, profiles_cfg.keys(), axes_cfg.keys(), new_defs.keys()),
    }


# --- kalibracja moment -> siła (etap 2 tematu K, ekran /sila) --------------


@app.get("/api/kalibracja")
async def get_kalibracja(user=Depends(require_operator)):
    """Punkty kalibracji moment->siła zapisane dla każdej osi."""
    return {
        "kalibracja": kalibracja.to_dict(kalibracja_cfg),
        "file": str(config.KALIBRACJA_FILE),
    }


@app.put("/api/kalibracja")
async def put_kalibracja(req: KalibracjaRequest, user=Depends(require_admin)):
    """Zapis punktów kalibracji — dane pomiarowe, nie parametr bezpieczeństwa."""
    global kalibracja_cfg
    try:
        new_cfg = kalibracja.parse_kalibracja(req.kalibracja)
    except kalibracja.KalibracjaError as exc:
        raise HTTPException(422, str(exc))

    try:
        kalibracja.save(config.KALIBRACJA_FILE, new_cfg)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.KALIBRACJA_FILE}: {exc}")
    kalibracja_cfg = new_cfg
    _log(user, "zapis kalibracji moment->siła")
    return {"ok": True, "kalibracja": kalibracja.to_dict(new_cfg)}


# --- cykl maszyny ---------------------------------------------------------


@app.get("/api/cycle")
async def get_cycle(user=Depends(require_operator)):
    """Definicja cyklu maszyny."""
    return {
        "cycle": cycle_cfg.to_dict(),
        "step_kinds": list(cycle.STEP_KINDS),
        "outputs": list(cycle.OUTPUT_NAMES),
        # nazwy definicji SMART — ekran cyklu buduje z nich listę wyboru
        "smart": sorted(smart_cfg),
        "file": str(config.CYCLE_FILE),
        "warnings": cycle.warnings(
            cycle_cfg, profiles_cfg.keys(), axes_cfg.keys(), smart_cfg.keys()
        ),
    }


@app.put("/api/cycle")
async def put_cycle(req: CycleRequest, user=Depends(require_admin)):
    """Zapis definicji cyklu: walidacja, plik, przekazanie do maszyny."""
    global cycle_cfg
    if machine.status.state in (MachineState.RUNNING, MachineState.HOMING):
        raise HTTPException(409, "nie można zmieniać cyklu w trakcie ruchu maszyny")
    try:
        new_cycle = cycle.parse_cycle({"name": req.name, "steps": req.steps})
    except cycle.CycleError as exc:
        raise HTTPException(422, str(exc))

    result = cycle.warnings(
        new_cycle, profiles_cfg.keys(), axes_cfg.keys(), smart_cfg.keys()
    )
    try:
        cycle.save(config.CYCLE_FILE, new_cycle)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.CYCLE_FILE}: {exc}")
    cycle_cfg = new_cycle
    machine.apply_cycle(new_cycle)
    # zmiana kroków WYJSCIE może osierocić opis wyjścia albo wejść w konflikt
    # z wyjściem wrzeciona — admin ma to zobaczyć teraz, nie przy starcie cyklu
    result = result + outputs.warnings(
        outputs_cfg,
        cycle.outputs_used(new_cycle),
        config.MACHINE_MODE != "sim",
        config.SPINDLE_OUTPUT,
    )
    _log(user, "zapis cyklu maszyny", f"{len(new_cycle.steps)} kroków")
    return {"ok": True, "cycle": new_cycle.to_dict(), "warnings": result}


@app.post("/api/machine/cycle/start")
async def start_cycle(
    req: CycleStartRequest | None = None, user=Depends(require_operator)
):
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
async def machine_home(user=Depends(require_operator)):
    try:
        # home() waliduje synchronicznie i sam uruchamia ruch w tle;
        # create_task() w tym miejscu gubiło błędy walidacji (zawsze 200).
        await machine.home()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/go-to-zero")
async def machine_go_to_zero(user=Depends(require_operator)):
    try:
        await machine.go_to_zero()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/start")
async def machine_start(user=Depends(require_operator)):
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
async def machine_reset(user=Depends(require_operator)):
    await machine.reset()
    return {"ok": True}


@app.post("/api/machine/jog")
async def machine_jog(req: JogRequest, user=Depends(require_operator)):
    distance = max(-config.JOG_MAX_STEP, min(config.JOG_MAX_STEP, req.distance))
    axis = req.axis.lower()
    feed = req.feed if req.feed is not None else machine.axis_jog_feed(axis)
    try:
        await machine.jog(axis, distance, feed)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/release")
async def machine_release(req: ReleaseRequest, user=Depends(require_operator)):
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
async def sim_safety_enable(req: SimEnableRequest, user=Depends(require_operator)):
    """Tylko symulator: przełączenie sygnału zezwolenia do testów.

    W trybie sprzętowym sygnał pochodzi z niezależnego systemu bezpieczeństwa
    (Global Stop na SC4-Hub) — nie da się go ustawić z oprogramowania.
    """
    if not isinstance(machine, SimulatedMachine):
        raise HTTPException(409, "dostępne tylko w trybie symulacji (MACHINE_MODE=sim)")
    machine.set_safety_enable(req.enabled)
    return {"ok": True, "safety_enable": req.enabled}


# --- ekran diagnostyczny (admin, temat G) --------------------------------


@app.get("/api/diagnostics")
async def get_diagnostics(user=Depends(require_admin)):
    """Wszystko, co admin musi zobaczyć w jednym miejscu, zanim ruszy maszynę.

    Świadomie zbiera też to, czego dziś **nie ma** albo co działa wyłącznie
    w symulatorze — ekran diagnostyczny, który pokazuje same zielone pola,
    byłby mylący.
    """
    hardware = config.MACHINE_MODE != "sim"
    return {
        "machine": {
            "mode": config.MACHINE_MODE,
            "hardware": hardware,
            "bridge": f"{config.BRIDGE_HOST}:{config.BRIDGE_PORT}" if hardware else None,
            "status": machine.status.to_dict(),
        },
        "safety": {
            "enable": machine.status.safety_enable,
            # Świadomie wymieniamy, czego NIE mamy — patrz docstring.
            "brak": [
                "sygnał drzwi/osłony nie jest czytany przez serwer (temat E)",
                "limit momentu nie dociera do sprzętu (etap 2b tematu B)",
                "zatrzymanie awaryjne realizuje wyłącznie obwód sprzętowy "
                "(E-stop / Global Stop) — nie ten panel",
            ],
        },
        "config": {
            "axes": axes.to_dict(axes_cfg),
            "axes_warnings": _axis_warnings(axes_cfg),
            "homing": _homing_payload(axes_cfg),
            "profiles": profiles.to_dict(profiles_cfg),
            "active_profile": machine.active_profile,
            "profile_warnings": _profile_warnings(profiles_cfg),
            "cycle": cycle_cfg.to_dict(),
            "cycle_warnings": cycle.warnings(
                cycle_cfg, profiles_cfg.keys(), axes_cfg.keys()
            ),
            "spindle": _spindle_payload(spindle_cfg),
            "outputs": _outputs_payload(outputs_cfg),
        },
        "auth": {
            "enabled": auth_enabled(),
            "users": [u.public() for u in users_cfg.values()],
            "active_sessions": sessions.active_count(),
            "file": str(config.USERS_FILE),
        },
        "audit": {
            "file": str(config.AUDIT_FILE),
            "exists": config.AUDIT_FILE.exists(),
            "entries": audit.tail(config.AUDIT_FILE, 100),
        },
    }


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


@app.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/", include_in_schema=False)
async def index(request: Request):
    return _page(request, "index.html", users.ROLE_OPERATOR)


@app.get("/editor", include_in_schema=False)
async def editor(request: Request):
    return _page(request, "editor.html", users.ROLE_TECHNOLOG)


@app.get("/axes", include_in_schema=False)
async def axes_page(request: Request):
    return _page(request, "axes.html", users.ROLE_ADMIN)


@app.get("/cycle", include_in_schema=False)
async def cycle_page(request: Request):
    return _page(request, "cycle.html", users.ROLE_ADMIN)


@app.get("/profiles", include_in_schema=False)
async def profiles_page(request: Request):
    return _page(request, "profiles.html", users.ROLE_ADMIN)


@app.get("/homing", include_in_schema=False)
async def homing_page(request: Request):
    return _page(request, "homing.html", users.ROLE_ADMIN)


@app.get("/diagnostics", include_in_schema=False)
async def diagnostics_page(request: Request):
    return _page(request, "diagnostics.html", users.ROLE_ADMIN)


@app.get("/smart", include_in_schema=False)
async def smart_page(request: Request):
    return _page(request, "smart.html", users.ROLE_ADMIN)


@app.get("/sila", include_in_schema=False)
async def sila_page(request: Request):
    return _page(request, "sila.html", users.ROLE_ADMIN)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
