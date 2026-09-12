"""Serwer maszyny — API REST (MES, programy, sterowanie) + panel WWW.

Uruchomienie (z katalogu server/):
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audit, axes, config, cycle, io_modbus, kalibracja, outputs, profiles, punkty, smart, spindle, users, zuzycie, zuzycie_alarmy
from .feetech_driver import COUNTS_PER_REV, FeetekDriver, FeetekError, position_to_mm
from .modbus_driver import ModbusDriver
from .modbus_protocol import ModbusError
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
    torque_warnings,
    validate_work_area,
)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """Uruchamia i zatrzymuje jedyny poller statusu sterownika."""
    task = None
    if isinstance(machine, SC4HubMachine):
        task = asyncio.create_task(_poll_loop())
    # Niezależne od trybu X/Y/Z (sim albo sc4hub) — magistrala Feetech to
    # osobny fizyczny kanał (RS485), może być podłączona w obu trybach.
    # Sam sobie nic nie robi, jeśli brak skonfigurowanych osi "feetech"
    # albo FEETECH_PORT (patrz _feetech_poll_loop).
    feetech_task = asyncio.create_task(_feetech_poll_loop())
    io_modbus_task = asyncio.create_task(_io_modbus_poll_loop())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    feetech_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await feetech_task
    io_modbus_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await io_modbus_task


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

# Definicje alarmów zużycia (temat M, krok 4) — dane pomocnicze, nie
# parametr bezpieczeństwa: błędny/brakujący plik nie przerywa startu
# (powód w app/zuzycie_alarmy.py; alarmy same w sobie nie sterują maszyną).
zuzycie_alarmy_cfg = zuzycie_alarmy.load(config.ZUZYCIE_ALARMY_FILE)
_zuzycie_alarm_status: list[zuzycie_alarmy.AlarmStatus] = []

# Nazwane kanały I/O modułów Waveshare Modbus RTU (temat L) — lampy,
# drzwi/osłona, Start/Stop, wrzeciono, watchdog. Dane pomocnicze, nie
# parametr bezpieczeństwa: błędny/brakujący plik nie przerywa startu
# (powód w app/io_modbus.py). Przypisanie kanałów w default_io() to
# ZAŁOŻENIE, nie potwierdzone okablowanie — patrz docstring modułu.
io_modbus_cfg = io_modbus.load(config.IO_MODBUS_FILE)
_io_modbus_status: dict = {"do": {}, "di": {}, "ai": {}, "watchdog": {"enabled": False}}
_watchdog_last_pulse: bool | None = None
_watchdog_last_change: float | None = None

# Kalibracja moment -> siła (etap 2 tematu K) — pary (moment %, siła N)
# wpisane po pomiarze siłomierzem. Dane pomocnicze do dobierania progów,
# nie parametr bezpieczeństwa: błędny/brakujący plik nie przerywa startu
# (powód w app/kalibracja.py).
kalibracja_cfg = kalibracja.load(config.KALIBRACJA_FILE)

# Nazwane punkty PTP (ekran /nauczanie i /punkty) — wygodny picker w
# edytorze programu, nie parametr bezpieczeństwa: błędny/brakujący plik
# nie przerywa startu (powód w app/punkty.py).
punkty_cfg = punkty.load(config.PUNKTY_FILE)

# Cykl maszyny — kroki poziomu admina wokół programu detalu. Pusty, dopóki
# nie zostanie zdefiniowany; błędny plik przerywa start (powód w app/cycle.py).
cycle_cfg = cycle.load(config.CYCLE_FILE)
machine.apply_cycle(cycle_cfg)


def _cycle_output_names() -> set[str]:
    """Wyjścia dostępne krokowi WYJSCIE cyklu: dwa stałe wyjścia Teknica
    (`cycle.OUTPUT_NAMES`) + kanały DO modułu Waveshare, po nazwie kanału
    (`do0`) ALBO etykiecie (`LG`) — jak `POST /api/machine/io-modbus/write`.
    Czyta `io_modbus_cfg` na żywo (global), więc zawsze aktualne po
    `PUT /api/io-modbus`, bez potrzeby odświeżania przy każdym wywołaniu."""
    names = set(cycle.OUTPUT_NAMES)
    for name, ch in io_modbus_cfg.do.items():
        names.add(name)
        if ch.label:
            names.add(ch.label)
    return names

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


_zuzycie_was_running = False

# Magistrala RS485 jest fizycznie WSPÓLNA i półdupleksowa — serwa FEETECH
# I moduły I/O Waveshare (temat L) wiszą na tym samym przewodzie/porcie.
# Wszystkie dostępy z WEWNĄTRZ tego procesu (_feetech_poll_loop,
# /api/machine/jog-feetech, _io_modbus_poll_loop) muszą się wykluczać,
# inaczej dwie jednoczesne transakcje kolidują na przewodzie (zaobserwowane
# fizycznie 2026-09-11: JOG na jednej osi + odczyt statusu w tym samym
# momencie dał "brak odpowiedzi" na DRUGIEJ, mimo że elektrycznie
# wszystko było w porządku). Nazwa historyczna ("feetech") — dziś chroni
# całą magistralę, nie tylko serwa. UWAGA: nie chroni przed zewnętrznymi
# skryptami ad-hoc spoza tego procesu (patrz
# docs/zmiany/modbus-io-waveshare.md, „kolizja z żywą usługą").
_feetech_lock = asyncio.Lock()

# JOG "koło" (tryb stałej prędkości, poprawka "ruch skokami" 2026-09-11,
# patrz docs/zmiany/jog-feetech-tryb-kolo.md): nazwa osi -> moment
# (`time.monotonic()`), do którego serwo ma jeszcze się kręcić. Każde
# wywołanie `/api/machine/jog-feetech` (heartbeat z przytrzymanego
# przycisku) przedłuża ten termin; `/api/machine/jog-feetech/stop`
# (puszczenie przycisku) go usuwa i zatrzymuje serwo od razu.
# `_feetech_poll_loop` jest strażnikiem NA WYPADEK utraty połączenia z
# przeglądarką (zamknięta karta, padła sieć) — bez tego serwo kręciłoby
# się bez końca, bo tryb koła nie ma wbudowanego "martwego człowieka".
_feetech_wheel_deadline: dict[str, float] = {}
_FEETECH_WHEEL_HEARTBEAT_TIMEOUT = 0.6  # s — > tick klienta (250ms), krótko na wypadek utraty połączenia
_FEETECH_WHEEL_POLL_INTERVAL = 0.15     # s — tylko gdy trwa JOG koła; inaczej 1.0s jak dotąd


async def _poll_loop() -> None:
    global _zuzycie_was_running, _zuzycie_alarm_status
    while True:
        with contextlib.suppress(MachineError):
            await machine.poll_status()
        # Nagrywanie przebiegu (moment/pozycja) do analizy po fakcie —
        # celowo POZA suppress() wyżej: ma nagrywać ostatni znany status
        # nawet gdy poll_status() akurat zawiódł, nie tylko gdy się uda.
        machine._record_sample()
        # Zużycie osi (temat M): dopisz podsumowanie DOKŁADNIE przy przejściu
        # RUNNING/PAUSED -> coś innego, czyli "po przebiegu, na spokojnie"
        # (cykl maszyny albo pojedynczy program) — `machine.recording` z
        # tego przebiegu żyje aż do startu następnego (patrz `_record_sample`),
        # więc jest tu jeszcze kompletne. Błąd zapisu nie może zamrozić tej
        # pętli — zuzycie.record_run() sam nie rzuca, ale osłona zostaje na
        # wypadek błędu programistycznego w nowym module.
        running = machine.status.state in (MachineState.RUNNING, MachineState.PAUSED)
        if _zuzycie_was_running and not running:
            try:
                zuzycie.record_run(
                    config.ZUZYCIE_DIR,
                    machine.recording,
                    torque_measured=machine.status.torque_source == "sterownik",
                )
                # Ocena alarmów zużycia (temat M, krok 4) — tu samo, w tym
                # samym miejscu co zapis danych, zgodnie z "po cyklu, na
                # spokojnie". Tylko OCENA; wysyłkę powiadomień robi wMES
                # (krok 5, nieustalone).
                _zuzycie_alarm_status = zuzycie_alarmy.evaluate(
                    zuzycie_alarmy_cfg,
                    zuzycie.summarize_today(config.ZUZYCIE_DIR),
                    zuzycie.read_trend(config.ZUZYCIE_DIR),
                )
            except Exception:
                pass
        _zuzycie_was_running = running
        await asyncio.sleep(0.2)


def _read_feetech_status(
    feetech_ids: dict[str, int], axes_cfg: dict[str, axes.AxisConfig]
) -> dict[str, dict]:
    """Blokujące (termios) — wywoływać przez `asyncio.to_thread`, nigdy
    bezpośrednio w pętli async, żeby nie zamrozić reszty serwera na czas
    odpytywania portu szeregowego. Błąd pojedynczej osi nie blokuje reszty —
    magistrala RS485 jest współdzielona, ale jedno milczące serwo nie
    powinno ukryć odczytu z pozostałych.

    `position_mm` (temat L, etap 2 kalibracji) obok surowego `position` —
    patrz zastrzeżenia w `feetech_driver.position_to_mm()`: to przeliczenie
    skali przez skok śruby (`mm_per_rev`), NIE pozycja bazowana względem
    zera obszaru roboczego (bazowanie osi FEETECH to jeszcze niezrobiony
    etap 3)."""
    result: dict[str, dict] = {}
    with FeetekDriver(config.FEETECH_PORT, baud=config.FEETECH_BAUD) as driver:
        for axis_name, servo_id in feetech_ids.items():
            try:
                position, load = driver.read_position_and_load(servo_id)
                entry = {"position": position, "load": load, "id": servo_id}
                axis_cfg = axes_cfg.get(axis_name)
                if axis_cfg is not None:
                    entry["position_mm"] = round(position_to_mm(position, axis_cfg.mm_per_rev), 3)
                result[axis_name] = entry
            except FeetekError as exc:
                result[axis_name] = {"error": str(exc), "id": servo_id}
    return result


def _feetech_jog(servo_id: int, speed_cw: int) -> None:
    """Blokujące (termios) — wywoływać przez `asyncio.to_thread`, jak
    `_read_feetech_status`.

    Poprawka 2026-09-11 ("ruch skokami"): TRYB KOŁA (`wheel_speed_cw`),
    nie pojedynczy mały przejazd pozycyjny jak dawniej (`move_relative_cw`)
    — serwo kręci się PŁYNNIE aż do jawnego `/jog-feetech/stop` albo
    strażnika w `_feetech_poll_loop`. `speed_cw` już ma znak (dodatnie/
    ujemne z `feetech_speed` wg kierunku) — patrz endpoint.
    Szczegóły: docs/zmiany/jog-feetech-tryb-kolo.md."""
    with FeetekDriver(config.FEETECH_PORT, baud=config.FEETECH_BAUD) as driver:
        driver.wheel_speed_cw(servo_id, speed_cw)


def _feetech_jog_stop(servo_id: int) -> None:
    """Blokujące — zatrzymuje JOG koła (prędkość 0, tryb z powrotem
    pozycyjny). Wywoływane zarówno z endpointu stop (puszczenie przycisku),
    jak i ze strażnika w `_feetech_poll_loop` (utracone połączenie)."""
    with FeetekDriver(config.FEETECH_PORT, baud=config.FEETECH_BAUD) as driver:
        driver.wheel_stop(servo_id)


def _feetech_wheel_stop_reason(
    axis_cfg: axes.AxisConfig | None, position_mm: float | None, deadline: float, now: float
) -> str | None:
    """Czysta funkcja (testowalna bez czekania na pętlę/timery) — decyduje,
    czy JOG koła danej osi ma się zatrzymać SAM, i dlaczego:

    - "watchdog": minął termin ostatniego heartbeatu (`/jog-feetech`) —
      przeglądarka przestała potwierdzać trzymanie przycisku (zamknięta
      karta, padła sieć) — dead man's switch dla trybu bez wbudowanego.
    - "limit": pozycja [mm] przekroczyła limit programowy osi. UWAGA: to
      najlepszy wysiłek, nie twardy limit — odczyt pozycji po RS485 trwa
      rzędu 0,1-0,3s (`_read_feetech_status`), więc przy większych
      prędkościach możliwy jest zauważalny naddźwig za limit, zwłaszcza
      na krótkich osiach (np. docisk, 7 mm zakresu). Docelowa twarda
      ochrona to limity przejazdu w samym serwie (EPROM), nieskonfigurowane
      jeszcze — patrz uwagi w docs/zmiany/jog-feetech-tryb-kolo.md.
    """
    if now > deadline:
        return "watchdog"
    if position_mm is not None and axis_cfg is not None:
        if not (axis_cfg.soft_min - 0.05 <= position_mm <= axis_cfg.soft_max + 0.05):
            return "limit"
    return None


def _feetech_move_to_and_wait(
    servo_id: int,
    position: int,
    speed: int,
    acc: int,
    load_limit: int | None,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.1,
) -> None:
    """Blokujące (termios) — jak `_feetech_jog`, ale pozycja ABSOLUTNA i
    CZEKA na koniec ruchu (rejestr MOVING) — krok RUCH cyklu ma się
    zakończyć dopiero, gdy oś naprawdę dojechała, nie od razu po wysłaniu
    komendy. Ten sam wzorzec co `tools/feetech_jog.py`.

    `load_limit` (z `AxisConfig.feetech_load_limit`, None = wyłączone) to
    WYŁĄCZNIE zabezpieczenie awaryjne — decyzja operatora 2026-09-12: RUCH
    ma normalnie dojeżdżać do zadanej pozycji, przekroczenie progu
    |obciążenia| przerywa ruch (`stop_position_move`) i rzuca błąd,
    zamiast być zwykłym sposobem zatrzymania. Sprawdzane w tej samej
    pętli, co odpytywanie MOVING — jeden odczyt (`read_position_and_load`)
    na iterację, bez dodatkowych rund po RS485."""
    with FeetekDriver(config.FEETECH_PORT, baud=config.FEETECH_BAUD) as driver:
        driver.move_to(servo_id, position, speed=speed, acc=acc)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            _, load = driver.read_position_and_load(servo_id)
            if load_limit is not None and abs(load) > load_limit:
                driver.stop_position_move(servo_id, speed=speed, acc=acc)
                raise FeetekError(
                    f"serwo {servo_id}: przeciążenie (|obciążenie|={abs(load)} > "
                    f"limit {load_limit}) — ruch przerwany"
                )
            if not driver.is_moving(servo_id):
                return
            time.sleep(poll_interval_s)
        raise FeetekError(f"serwo {servo_id}: przekroczono czas oczekiwania na koniec ruchu")


async def _feetech_cycle_move(axis: str, target_mm: float) -> None:
    """Wstrzyknięte do `Machine.feetech_move` (temat L, etap 4 — osie
    FEETECH pełnoprawne w cyklu maszyny, zamówienie 2026-09-11). Patrz
    komentarz przy `self.feetech_move` w `machine.py` — to jedyny szew
    między `Machine` a `FeetekDriver`/RS485.

    Przelicza mm na jednostki rejestru ODWROTNOŚCIĄ `position_to_mm()` —
    te same zastrzeżenia: bez bazowania (etap 3) zero mm to fabryczne zero
    enkodera serwa, NIE zero obszaru roboczego maszyny."""
    feetech_ids = axes.feetech_axes(machine.axes)
    if axis not in feetech_ids:
        raise MachineError(f"oś {axis.upper()} nie jest skonfigurowana jako FEETECH")
    if not config.FEETECH_PORT:
        raise MachineError("FEETECH_PORT nieskonfigurowany — magistrala RS485 niedostępna")
    axis_cfg = machine.axes[axis]
    servo_id = feetech_ids[axis]
    position = round(target_mm / axis_cfg.mm_per_rev * COUNTS_PER_REV)
    try:
        async with _feetech_lock:
            await asyncio.to_thread(
                _feetech_move_to_and_wait,
                servo_id,
                position,
                axis_cfg.feetech_speed,
                axis_cfg.feetech_acc,
                axis_cfg.feetech_load_limit,
            )
    except FeetekError as exc:
        raise MachineError(f"oś {axis.upper()} (FEETECH): {exc}")


# Wstrzyknięcie (temat L, etap 4) — patrz komentarz przy `Machine.feetech_move`
# w machine.py. Ustawione bezwarunkowo, niezależnie od MACHINE_MODE: RS485 to
# osobny fizyczny kanał od X/Y/Z (tak samo jak `_feetech_poll_loop`).
machine.feetech_move = _feetech_cycle_move


async def _feetech_poll_loop() -> None:
    """Odpytuje magistralę Feetech co ~1s — osobno od `_poll_loop` (X/Y/Z),
    wolniej (odczyt po termios jest rzędu 0,1-0,3s na oś, nie mieści się w
    budżecie 200ms tamtej pętli) i niezależnie od trybu MACHINE_MODE (RS485
    to osobny fizyczny kanał, może być podłączony razem z symulatorem X/Y/Z
    do testów). Etap 1 tematu L — patrz
    docs/architektura-wielu-drajwerow-osi.md. Jednostki rejestru plus
    `position_mm` przeliczone przez skok śruby (etap 2, `feetech_driver.
    position_to_mm()`) — bez bazowania (etap 3, wciąż niezrobiony).

    Gdy trwa JOG koła (`_feetech_wheel_deadline` niepuste — poprawka
    "ruch skokami" 2026-09-11) odpytuje częściej (`_FEETECH_WHEEL_POLL_
    INTERVAL`) i pełni rolę strażnika: zatrzymuje oś, jeśli minął termin
    heartbeatu albo pozycja przekroczyła limit programowy — patrz
    `_feetech_wheel_stop_reason()`."""
    while True:
        await asyncio.sleep(_FEETECH_WHEEL_POLL_INTERVAL if _feetech_wheel_deadline else 1.0)
        feetech_ids = axes.feetech_axes(machine.axes)
        if not feetech_ids or not config.FEETECH_PORT:
            continue
        try:
            async with _feetech_lock:
                machine.status.feetech_raw = await asyncio.to_thread(
                    _read_feetech_status, feetech_ids, machine.axes
                )
                now = time.monotonic()
                for axis, deadline in list(_feetech_wheel_deadline.items()):
                    servo_id = feetech_ids.get(axis)
                    if servo_id is None:
                        _feetech_wheel_deadline.pop(axis, None)
                        continue
                    position_mm = machine.status.feetech_raw.get(axis, {}).get("position_mm")
                    reason = _feetech_wheel_stop_reason(
                        machine.axes.get(axis), position_mm, deadline, now
                    )
                    if reason:
                        _feetech_wheel_deadline.pop(axis, None)
                        with contextlib.suppress(FeetekError):
                            await asyncio.to_thread(_feetech_jog_stop, servo_id)
        except Exception:
            pass  # magistrala niedostępna teraz — spróbuj ponownie za chwilę


def _read_io_modbus(cfg: io_modbus.IoConfig) -> dict:
    """Blokujące (termios) — wywoływać przez `asyncio.to_thread` pod
    `_feetech_lock`. Jedno połączenie na port (9600 baud), oba moduły
    Waveshare na różnych adresach Modbus (`DIGITAL_MODULE_ADDRESS`,
    `ANALOG_MODULE_ADDRESS`) — nie trzeba osobnych połączeń per moduł."""
    result: dict = {"do": {}, "di": {}, "ai": {}}
    with ModbusDriver(config.MODBUS_IO_PORT, baud=config.MODBUS_IO_BAUD) as driver:
        try:
            do_values = driver.read_digital_outputs(io_modbus.DIGITAL_MODULE_ADDRESS)
            for name, ch in cfg.do.items():
                result["do"][name] = {"label": ch.label, "value": do_values[int(name[2:])]}
        except ModbusError as exc:
            result["do_error"] = str(exc)
        try:
            di_values = driver.read_digital_inputs(io_modbus.DIGITAL_MODULE_ADDRESS)
            for name, ch in cfg.di.items():
                result["di"][name] = {"label": ch.label, "value": di_values[int(name[2:])]}
        except ModbusError as exc:
            result["di_error"] = str(exc)
        try:
            ai_values = driver.read_analog_channels(io_modbus.ANALOG_MODULE_ADDRESS)
            for name, ch in cfg.ai.items():
                result["ai"][name] = {"label": ch.label, "value": ai_values[int(name[2:])]}
        except ModbusError as exc:
            result["ai_error"] = str(exc)
    return result


async def _io_modbus_poll_loop() -> None:
    """Odpytuje moduły I/O Waveshare co ~1s (albo `watchdog.interval_s`,
    jeśli watchdog jest włączony) — osobno od pętli serw, ale pod tym
    samym `_feetech_lock` (współdzielona magistrala fizyczna). Temat L,
    zamówienie użytkownika 2026-09-11 — patrz
    docs/zmiany/modbus-io-waveshare.md.

    Watchdog impulsów drzwi: NIE jest certyfikowaną funkcją bezpieczeństwa
    (jak żaden odczyt sygnału drzwi programowo w tym projekcie) — to
    diagnostyka, wykrywa czy sygnał impulsowy w ogóle się zmienia
    (heartbeat), nie zastępuje sprzętowego Global Stop.
    """
    global _io_modbus_status, _watchdog_last_pulse, _watchdog_last_change
    while True:
        interval = io_modbus_cfg.watchdog.interval_s if io_modbus_cfg.watchdog.enabled else 1.0
        await asyncio.sleep(max(0.2, interval))
        if not config.MODBUS_IO_PORT:
            continue
        try:
            async with _feetech_lock:
                result = await asyncio.to_thread(_read_io_modbus, io_modbus_cfg)
        except Exception:
            continue

        wd = io_modbus_cfg.watchdog
        if wd.enabled and wd.pulse_channel in result.get("di", {}):
            pulse_value = result["di"][wd.pulse_channel]["value"]
            now = time.monotonic()
            if _watchdog_last_pulse is None or pulse_value != _watchdog_last_pulse:
                _watchdog_last_pulse = pulse_value
                _watchdog_last_change = now
            age = (now - _watchdog_last_change) if _watchdog_last_change is not None else None
            result["watchdog"] = {
                "enabled": True,
                "pulse_channel": wd.pulse_channel,
                "guard_channel": wd.guard_channel,
                "guard_value": result.get("di", {}).get(wd.guard_channel, {}).get("value"),
                "age_s": round(age, 1) if age is not None else None,
                "ok": age is not None and age < wd.stale_after_s,
            }
        else:
            result["watchdog"] = {"enabled": False}
        _io_modbus_status = result


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


class JogFeetechRequest(BaseModel):
    """JOG dla osi FEETECH — tryb koła (stała prędkość, poprawka 2026-09-11),
    kierunek zgodny/przeciwny do zegara (`DIRECTION_SIGN_CW`), NIE mm/+-,
    bo znak mm nie jest jeszcze ujednolicony między osiami (etap 3,
    bazowanie, wciąż niezrobione)."""

    axis: str
    kierunek: str = Field(..., pattern="^(cw|ccw)$")


class JogFeetechStopRequest(BaseModel):
    """Puszczenie przycisku JOG — zatrzymuje tryb koła od razu, nie czeka
    na strażnika (`_feetech_wheel_deadline`)."""

    axis: str


class IoModbusConfigRequest(BaseModel):
    """Konfiguracja nazwanych kanałów I/O Modbus z ekranu (temat L)."""

    do: dict[str, dict] = Field(default_factory=dict)
    di: dict[str, dict] = Field(default_factory=dict)
    ai: dict[str, dict] = Field(default_factory=dict)
    watchdog: dict = Field(default_factory=dict)


class IoModbusWriteRequest(BaseModel):
    """Zapis jednego wyjścia cyfrowego modułu I/O — po nazwie kanału
    (`do0`..`do7`) albo po etykiecie z konfiguracji (np. `LG`)."""

    channel: str
    on: bool


class ReleaseRequest(BaseModel):
    """Luzowanie osi: pojedyncza oś albo 'all' (wszystkie na raz)."""

    axis: str = Field(..., pattern="^([xyzXYZ]|all|ALL)$")
    released: bool


class HandGuideStartRequest(BaseModel):
    """Start prowadzenia za rękę (ekran /nauczanie) — silnik zostaje na
    normalnym limicie momentu, wykrywamy tylko małą zmianę odczytu
    momentu względem spoczynku (docs/prowadzenie-za-reke.md)."""

    axis: str = Field(..., pattern="^[xyzXYZ]$")
    threshold_pct: float = Field(0.3, ge=0.05, le=20.0, description="próg wykrycia nacisku [%]")
    feed: float = Field(400.0, ge=10.0, le=3000.0, description="posuw kroku [mm/min]")
    step_mm: float = Field(1.0, ge=0.05, le=10.0, description="dystans jednego kroku [mm]")


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


class ZuzycieAlarmyRequest(BaseModel):
    """Definicje alarmów zużycia z ekranu /zuzycie (temat M, krok 4)."""

    alarmy: dict[str, dict] = Field(
        ..., description="nazwa alarmu -> {os, metryka, okres, prog, aktywny, note}"
    )


class PunktyRequest(BaseModel):
    """Nazwane punkty PTP z ekranów `/nauczanie` i `/punkty`.

    Jak przy SMART i kalibracji — walidacją zajmuje się app/punkty.py, żeby
    operator zobaczył komunikat po polsku z nazwą punktu.
    """

    points: dict[str, dict] = Field(..., description="nazwa punktu -> {x, y, z, note}")


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
    # Limit momentu dociera do sprzętu (TRQLIMIT, etap 2b tematu B,
    # zweryfikowane 2026-09-01: mostek odbiera i stosuje wartość). Wcześniej
    # był tu odwrotny komunikat ("nie dociera do sprzętu") — nieaktualny od
    # czasu wdrożenia etapu 2b, zostawiony przez pomyłkę i mylący operatora
    # podczas testu fizycznego. Usunięty, zamiast podmieniony na nowy: sam
    # transport do serwa nie jest już czymś, co trzeba operatorowi tłumaczyć
    # przy każdym zapisie profilu.
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
        result["warnings"] = smart_warnings(program, smart_cfg.keys()) + torque_warnings(program)
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
        # brakująca definicja SMART albo MOMENT nie blokuje zapisu (plik .prg
        # jest samodzielny), ale technolog musi to zobaczyć od razu, a nie
        # dopiero przy starcie na maszynie
        "warnings": smart_warnings(program, smart_cfg.keys()) + torque_warnings(program),
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
        + cycle.warnings(
            cycle_cfg, profiles_cfg.keys(), axes_cfg.keys(), new_defs.keys(), _cycle_output_names()
        ),
    }


# --- nazwane punkty PTP (ekrany /nauczanie i /punkty) ----------------------


@app.get("/api/punkty")
async def get_punkty(user=Depends(require_operator)):
    """Lista nazwanych punktów — do pickera w edytorze i ekranu /punkty."""
    return {
        "points": punkty.to_dict(punkty_cfg),
        "file": str(config.PUNKTY_FILE),
    }


@app.put("/api/punkty")
async def put_punkty(req: PunktyRequest, user=Depends(require_admin)):
    """Zapis całej listy punktów — usunięcie punktu to pominięcie go w ciele żądania."""
    global punkty_cfg
    try:
        new_points = punkty.parse_points({"points": req.points})
    except punkty.PunktyError as exc:
        raise HTTPException(422, str(exc))

    try:
        punkty.save(config.PUNKTY_FILE, new_points)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.PUNKTY_FILE}: {exc}")
    punkty_cfg = new_points
    _log(user, "zapis nazwanych punktów", ", ".join(sorted(new_points)))
    return {"ok": True, "points": punkty.to_dict(new_points)}


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
        # dwa wyjścia Teknica + kanały DO modułu Waveshare PO NAZWIE kanału
        # (stabilny identyfikator, np. "do3" — nie etykieta, która może się
        # zmienić z ekranu /io-modbus). Etykiety ekran dociąga z GET
        # /api/io-modbus, do samego wyświetlania w liście wyboru.
        "outputs": sorted(cycle.OUTPUT_NAMES) + sorted(io_modbus_cfg.do.keys()),
        # nazwy definicji SMART — ekran cyklu buduje z nich listę wyboru
        "smart": sorted(smart_cfg),
        "file": str(config.CYCLE_FILE),
        "warnings": cycle.warnings(
            cycle_cfg, profiles_cfg.keys(), axes_cfg.keys(), smart_cfg.keys(), _cycle_output_names()
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
        new_cycle, profiles_cfg.keys(), axes_cfg.keys(), smart_cfg.keys(), _cycle_output_names()
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


@app.get("/api/przebieg")
async def get_przebieg(user=Depends(require_operator)):
    """Nagrany przebieg momentu/pozycji ostatniego uruchomienia (ekran
    /sila) — próbki co 200 ms z `_poll_loop`, żeby dało się przeanalizować
    po fakcie to, co na żywo dzieje się za szybko."""
    return {"samples": machine.recording}


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
    """Zatrzymanie — musi zwrócić czytelny błąd, nie 500, jeśli komenda do
    mostka się nie powiedzie (np. odrzucona przez sFoundation). To jedyny
    endpoint sterowania, który wcześniej nie łapał MachineError — znalezione
    2026-09-01, gdy błąd SDK na węźle osi ("Node @ 1 error") przy próbie
    STOP wywalił nieobsłużony wyjątek zamiast komunikatu."""
    try:
        await machine.stop()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/reset")
async def machine_reset(user=Depends(require_operator)):
    """Kasuje alarm — musi zwrócić czytelny błąd, nie 500, jeśli mostek
    odrzuci komendę (ten sam brakujący wzorzec co przy STOP, znaleziony
    2026-09-01 — RESET był jedynym pozostałym endpointem sterowania bez
    tej obsługi, znalezione 2026-09-02 gdy Kasuj alarm nic nie robił)."""
    try:
        await machine.reset()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
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


@app.post("/api/machine/jog-feetech")
async def machine_jog_feetech(req: JogFeetechRequest, user=Depends(require_operator)):
    """JOG dla osi FEETECH — TRYB KOŁA (stała prędkość, poprawka 2026-09-11:
    dawny "ruch skokami" był powtarzaniem drobnych przejazdów pozycyjnych co
    250ms, każdy z osobnym rozpędzaniem/hamowaniem). Niezależne od
    `Machine.jog()` (ścieżka X/Y/Z przez Teknika nietknięta, zgodnie z
    decyzją „Feetech obok, nie w środku").

    Wywołanie to HEARTBEAT: przeglądarka wysyła je co ~250ms, dopóki
    przycisk jest trzymany — każde przedłuża `_feetech_wheel_deadline`.
    Puszczenie przycisku wywołuje `/jog-feetech/stop`; jeśli z jakiegoś
    powodu nie dotrze (zamknięta karta, padła sieć), `_feetech_poll_loop`
    zatrzyma serwo samo po przekroczeniu terminu. Kierunek zgodny/przeciwny
    do zegara (`DIRECTION_SIGN_CW`), NIE mm — znak mm nie jest jeszcze
    ujednolicony między osiami (bazowanie, etap 3). Prędkość z konfiguracji
    osi (`feetech_speed`, ekran /axes) — to samo pole co maksymalna
    prędkość ruchu pozycyjnego w RUCH cyklu.
    """
    axis = req.axis.lower()
    feetech_ids = axes.feetech_axes(machine.axes)
    if axis not in feetech_ids:
        raise HTTPException(404, f"oś '{axis}' nie jest skonfigurowana jako FEETECH")
    if not config.FEETECH_PORT:
        raise HTTPException(409, "FEETECH_PORT nieskonfigurowany — magistrala niedostępna")
    servo_id = feetech_ids[axis]
    axis_cfg = machine.axes[axis]
    speed_cw = axis_cfg.feetech_speed if req.kierunek == "cw" else -axis_cfg.feetech_speed
    try:
        async with _feetech_lock:
            await asyncio.to_thread(_feetech_jog, servo_id, speed_cw)
    except (FeetekError, KeyError) as exc:
        raise HTTPException(409, str(exc))
    _feetech_wheel_deadline[axis] = time.monotonic() + _FEETECH_WHEEL_HEARTBEAT_TIMEOUT
    return {"ok": True}


@app.post("/api/machine/jog-feetech/stop")
async def machine_jog_feetech_stop(req: JogFeetechStopRequest, user=Depends(require_operator)):
    """Puszczenie przycisku JOG — zatrzymuje tryb koła NATYCHMIAST, nie
    czeka na strażnika w `_feetech_poll_loop`."""
    axis = req.axis.lower()
    feetech_ids = axes.feetech_axes(machine.axes)
    if axis not in feetech_ids:
        raise HTTPException(404, f"oś '{axis}' nie jest skonfigurowana jako FEETECH")
    _feetech_wheel_deadline.pop(axis, None)
    if not config.FEETECH_PORT:
        return {"ok": True}  # nie ma czego zatrzymywać — magistrala i tak niedostępna
    servo_id = feetech_ids[axis]
    try:
        async with _feetech_lock:
            await asyncio.to_thread(_feetech_jog_stop, servo_id)
    except FeetekError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


# --- I/O modułów Waveshare Modbus RTU (temat L) ---------------------------


def _io_modbus_write(channel_name: str, on: bool) -> None:
    """Blokujące — wywoływać przez `asyncio.to_thread` pod `_feetech_lock`."""
    with ModbusDriver(config.MODBUS_IO_PORT, baud=config.MODBUS_IO_BAUD) as driver:
        driver.write_digital_output(io_modbus.DIGITAL_MODULE_ADDRESS, int(channel_name[2:]), on)


def _resolve_io_modbus_channel(channel: str) -> str:
    """Nazwa kanału (`do0`) albo etykieta (`LG`) -> nazwa kanału. Rzuca
    `KeyError`, jeśli nieznany — wywołujący decyduje, jak to zgłosić
    (HTTPException 404 z endpointu, MachineError z kroku cyklu)."""
    if channel in io_modbus_cfg.do:
        return channel
    found = io_modbus_cfg.channel_by_label(io_modbus_cfg.do, channel)
    if found is None:
        raise KeyError(channel)
    return found


async def _io_modbus_cycle_write(channel: str, on: bool) -> None:
    """Wstrzyknięte do `Machine.io_modbus_write` (zamówienie 2026-09-12:
    „dodać nowe I/O do wykorzystania w cyklu maszyny, zostaw dwa
    istniejące" — krok WYJSCIE steruje teraz też kanałami DO modułu
    Waveshare, OBOK dwóch dotychczasowych wyjść Teknica). Patrz komentarz
    przy `self.io_modbus_write` w `machine.py` — ten sam powód co
    `feetech_move`: Machine nie zna ModbusDriver/RS485 wprost."""
    try:
        resolved = _resolve_io_modbus_channel(channel)
    except KeyError:
        raise MachineError(f"nieznany kanał wyjścia I/O Modbus '{channel}'")
    if not config.MODBUS_IO_PORT:
        raise MachineError("MODBUS_IO_PORT nieskonfigurowany — magistrala RS485 niedostępna")
    try:
        async with _feetech_lock:
            await asyncio.to_thread(_io_modbus_write, resolved, on)
    except ModbusError as exc:
        raise MachineError(f"wyjście '{channel}' (I/O Modbus): {exc}")


# Wstrzyknięcie — patrz komentarz przy `Machine.io_modbus_write` w
# machine.py. Bezwarunkowe, jak `machine.feetech_move`: RS485 to osobny
# fizyczny kanał, niezależny od MACHINE_MODE.
machine.io_modbus_write = _io_modbus_cycle_write


@app.get("/api/io-modbus")
async def get_io_modbus(user=Depends(require_technolog)):
    """Bieżące wartości (z ostatniego odpytania pętli, nie na żywo przy
    każdym zapytaniu — jak `feetech_raw`) + konfiguracja nazw kanałów."""
    return {"status": _io_modbus_status, "config": io_modbus_cfg.to_dict()}


@app.put("/api/io-modbus")
async def put_io_modbus(req: IoModbusConfigRequest, user=Depends(require_admin)):
    global io_modbus_cfg
    try:
        new_cfg = io_modbus.IoConfig.from_dict(req.model_dump())
    except io_modbus.IoConfigError as exc:
        raise HTTPException(422, str(exc))
    try:
        io_modbus.save(config.IO_MODBUS_FILE, new_cfg)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.IO_MODBUS_FILE}: {exc}")
    io_modbus_cfg = new_cfg
    _log(user, "zapis konfiguracji I/O Modbus", "")
    return {"ok": True, "config": new_cfg.to_dict()}


@app.post("/api/machine/io-modbus/write")
async def machine_io_modbus_write(req: IoModbusWriteRequest, user=Depends(require_operator)):
    """Zapis jednego wyjścia — po nazwie kanału (`do0`) albo etykiecie
    (`LG`). Tylko moduł cyfrowy ma wyjścia — moduł analogowy to same
    wejścia pomiarowe."""
    try:
        channel = _resolve_io_modbus_channel(req.channel)
    except KeyError:
        raise HTTPException(404, f"nieznany kanał wyjścia '{req.channel}'")
    if not config.MODBUS_IO_PORT:
        raise HTTPException(409, "MODBUS_IO_PORT nieskonfigurowany — magistrala niedostępna")
    try:
        async with _feetech_lock:
            await asyncio.to_thread(_io_modbus_write, channel, req.on)
    except ModbusError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True, "channel": channel, "on": req.on}


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


@app.post("/api/machine/hand-guide/start")
async def hand_guide_start(req: HandGuideStartRequest, user=Depends(require_admin)):
    """Rozpoczyna prowadzenie za rękę jednej osi — patrz docs/prowadzenie-za-reke.md.

    Wymaga uprawnień admina jak reszta ekranu /nauczanie — to nie jest
    zwykły ruch operatora, tylko narzędzie do przygotowania punktów.
    """
    try:
        await machine.hand_guide_start(req.axis.lower(), req.threshold_pct, req.feed, req.step_mm)
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/machine/hand-guide/tick")
async def hand_guide_tick(user=Depends(require_admin)):
    """Jedno wywołanie pętli — przeglądarka woła je wielokrotnie, jak
    przytrzymanie JOG. Przerwanie wywołań po prostu kończy prowadzenie."""
    try:
        return await machine.hand_guide_tick()
    except MachineError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/machine/hand-guide/stop")
async def hand_guide_stop(user=Depends(require_admin)):
    await machine.hand_guide_stop()
    return {"ok": True}


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


# --- zużycie osi (temat M, krok 3-4) --------------------------------------


@app.get("/api/zuzycie")
async def get_zuzycie(user=Depends(require_technolog)):
    """Podsumowanie bieżącej doby (na żywo) + trwały trend + stan alarmów
    zużycia (temat M). Jednostki: dystans w mm (suma), moment w % maksimum
    (średnia/maksimum z przebiegów danego dnia).

    Alarmy: ocena z ostatniego zakończonego przebiegu (`_poll_loop`,
    zaraz po `zuzycie.record_run()`) — NIE liczona na żywo przy każdym
    zapytaniu, z tego samego powodu co zapis danych („po cyklu, na
    spokojnie"). Wysyłkę powiadomień (e-mail, MES/FAP) robi wMES, nie ten
    serwer — krok 5, nieustalone jeszcze, jak wMES ma to odczytać.
    """
    return {
        "dzisiaj": zuzycie.summarize_today(config.ZUZYCIE_DIR),
        "trend": zuzycie.read_trend(config.ZUZYCIE_DIR),
        "alarmy": [s.to_dict() for s in _zuzycie_alarm_status],
    }


@app.get("/api/zuzycie/alarmy")
async def get_zuzycie_alarmy(user=Depends(require_technolog)):
    """Definicje alarmów zużycia (krok 4) — CRUD wzorem `/api/smart`."""
    return {
        "alarmy": zuzycie_alarmy.to_dict(zuzycie_alarmy_cfg),
        "metryki": list(zuzycie_alarmy.METRYKI),
        "okresy": list(zuzycie_alarmy.OKRESY),
        "file": str(config.ZUZYCIE_ALARMY_FILE),
    }


@app.put("/api/zuzycie/alarmy")
async def put_zuzycie_alarmy(req: ZuzycieAlarmyRequest, user=Depends(require_admin)):
    global zuzycie_alarmy_cfg
    try:
        new_defs = zuzycie_alarmy.parse_definitions({"alarmy": req.alarmy})
    except zuzycie_alarmy.AlarmError as exc:
        raise HTTPException(422, str(exc))
    try:
        zuzycie_alarmy.save(config.ZUZYCIE_ALARMY_FILE, new_defs)
    except OSError as exc:
        raise HTTPException(500, f"nie udało się zapisać {config.ZUZYCIE_ALARMY_FILE}: {exc}")
    zuzycie_alarmy_cfg = new_defs
    _log(user, "zapis definicji alarmów zużycia", ", ".join(sorted(new_defs)))
    return {"ok": True, "alarmy": zuzycie_alarmy.to_dict(new_defs)}


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
                cycle_cfg, profiles_cfg.keys(), axes_cfg.keys(), output_names=_cycle_output_names()
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


@app.get("/punkty", include_in_schema=False)
async def punkty_page(request: Request):
    return _page(request, "punkty.html", users.ROLE_ADMIN)


@app.get("/nauczanie", include_in_schema=False)
async def nauczanie_page(request: Request):
    return _page(request, "nauczanie.html", users.ROLE_ADMIN)


@app.get("/zuzycie", include_in_schema=False)
async def zuzycie_page(request: Request):
    # ROLE_ADMIN, nie TECHNOLOG jak w kroku 3 — strona ma teraz też CRUD
    # definicji alarmów (krok 4), a PUT /api/zuzycie/alarmy wymaga admina;
    # spójne z /smart (ta sama różnica: podgląd niżej, edycja wyżej).
    return _page(request, "zuzycie.html", users.ROLE_ADMIN)


@app.get("/io-modbus", include_in_schema=False)
async def io_modbus_page(request: Request):
    # ROLE_ADMIN jak /zuzycie — ekran ma też edycję etykiet/watchdogu
    # (PUT /api/io-modbus wymaga admina), nie tylko podgląd.
    return _page(request, "io-modbus.html", users.ROLE_ADMIN)


@app.get("/help", include_in_schema=False)
async def help_page(request: Request):
    # ROLE_OPERATOR — instrukcja obsługi (zamówienie 2026-09-12) ma być
    # czytelna dla każdego zalogowanego, nie tylko admina; treść sama
    # opisuje, które ekrany są admin-only.
    return _page(request, "help.html", users.ROLE_OPERATOR)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
