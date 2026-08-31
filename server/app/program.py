"""Parser i serializator plików programu (.prg) — formaty 1, 2, 3, 4 i 5.

Format opisany w docs/FORMAT_PROGRAMU.md: sekcja [NAGLOWEK] z parami
KLUCZ;WARTOSC oraz sekcja [OPERACJE] z tabelą rozdzielaną średnikami.
Komunikaty błędów po polsku, z numerem linii — trafiają wprost do
technologa/operatora.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .smart import is_valid_name

NC12_RE = re.compile(r"^\d{12}$")

# Format 1: osiem kolumn. Format 2 dokłada parametry operacji.
# Parser czyta wszystkie wersje, zapis idzie zawsze w najnowszej — starsze
# pliki awansują przy pierwszym zapisie w edytorze.
OPERATIONS_HEADER_V1 = ["LP", "OPERACJA", "X", "Y", "Z", "X2", "Y2", "UWAGI"]
OPERATIONS_HEADER_V2 = [
    "LP",
    "OPERACJA",
    "X",
    "Y",
    "Z",
    "X2",
    "Y2",
    "POSUW",
    "PRZEJSCIA",
    "PRZYROST",
    "UWAGI",
]
# Format 3 dokłada OBROTY — potrzebne operacji WRZECIONO. Świadomie osobna
# kolumna zamiast doklejania obrotów do POSUW: przeciążanie znaczenia kolumn
# mści się przy czytaniu pliku w Excelu.
OPERATIONS_HEADER_V3 = [
    "LP",
    "OPERACJA",
    "X",
    "Y",
    "Z",
    "X2",
    "Y2",
    "POSUW",
    "OBROTY",
    "PRZEJSCIA",
    "PRZYROST",
    "UWAGI",
]
# Format 4 dokłada MOMENT — limit siły (momentu silnika) dla pojedynczej
# operacji, w procentach [%]. Puste = dziedziczy z aktywnego profilu
# parametrów (docs/zmiany/profile-parametrow-etap2.md). Jak OBROTY w formacie
# 3: osobna kolumna, nie przeciążanie znaczenia POSUW.
OPERATIONS_HEADER_V4 = [
    "LP",
    "OPERACJA",
    "X",
    "Y",
    "Z",
    "X2",
    "Y2",
    "POSUW",
    "OBROTY",
    "MOMENT",
    "PRZEJSCIA",
    "PRZYROST",
    "UWAGI",
]
# Format 5 dokłada SMART — nazwę definicji funkcji SMART, którą technolog
# wstawia po punkcie (temat K, docs/funkcje-smart.md). W kolumnie jest sama
# nazwa; parametry siedzą w definicji (config/smart.json), bo ten sam zestaw
# ma działać tak samo w programie technologa i w cyklu maszyny.
OPERATIONS_HEADER_V5 = [
    "LP",
    "OPERACJA",
    "X",
    "Y",
    "Z",
    "X2",
    "Y2",
    "POSUW",
    "OBROTY",
    "MOMENT",
    "PRZEJSCIA",
    "PRZYROST",
    "SMART",
    "UWAGI",
]
OPERATIONS_HEADER = OPERATIONS_HEADER_V5  # domyślny przy zapisie
SUPPORTED_FORMATS = {
    1: OPERATIONS_HEADER_V1,
    2: OPERATIONS_HEADER_V2,
    3: OPERATIONS_HEADER_V3,
    4: OPERATIONS_HEADER_V4,
    5: OPERATIONS_HEADER_V5,
}

REQUIRED_HEADER_KEYS = [
    "FORMAT",
    "PROGRAM",
    "NAZWA",
    "OBROTY_FREZU",
    "POSUW_ROBOCZY",
    "POSUW_DOJAZDU",
    "Z_BEZPIECZNE",
]

OPTIONAL_HEADER_KEYS = ["MATERIAL", "AUTOR", "DATA"]

# rodzaj operacji -> kolumny, które muszą być wypełnione
OPERATION_TYPES = {
    "PUNKT": ["X", "Y", "Z"],
    "LINIA": ["X", "Y", "Z", "X2", "Y2"],
    "PROSTOKAT": ["X", "Y", "Z", "X2", "Y2"],  # narożniki przeciwległe
    "SZYBKI": ["X", "Y"],                      # przejazd na Z bezpiecznym
    "WRZECIONO": ["OBROTY"],                   # zmiana obrotów w trakcie programu
    "SMART": ["SMART"],                        # wywołanie definicji SMART
    "PAUZA": [],
}

# operacje skrawające — tylko one przyjmują przejścia na głębokość
CUTTING_TYPES = {"PUNKT", "LINIA", "PROSTOKAT"}


class ProgramError(Exception):
    """Błąd składni lub walidacji pliku programu."""

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        prefix = f"linia {line}: " if line else ""
        super().__init__(prefix + message)


@dataclass
class Operation:
    lp: int
    op_type: str
    x: float | None = None
    y: float | None = None
    z: float | None = None
    x2: float | None = None
    y2: float | None = None
    # parametry formatu 2 — puste znaczy "domyślne z nagłówka programu"
    feed: float | None = None          # posuw roboczy tylko dla tej operacji
    rpm: float | None = None           # obroty wrzeciona (operacja WRZECIONO)
    passes: int | None = None          # liczba przejść na głębokość
    depth_step: float | None = None    # przyrost głębokości na przejście [mm]
    torque_pct: float | None = None    # limit momentu tylko dla tej operacji [%]
    # nazwa definicji SMART (format 5) — puste dla wszystkich operacji poza SMART
    smart: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "lp": self.lp,
            "op_type": self.op_type,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "x2": self.x2,
            "y2": self.y2,
            "feed": self.feed,
            "rpm": self.rpm,
            "passes": self.passes,
            "depth_step": self.depth_step,
            "torque_pct": self.torque_pct,
            "smart": self.smart,
            "note": self.note,
        }


@dataclass
class Program:
    number: str
    name: str
    spindle_rpm: float
    feed_work: float
    feed_travel: float
    z_safe: float
    material: str = ""
    author: str = ""
    date: str = ""
    operations: list[Operation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "material": self.material,
            "author": self.author,
            "date": self.date,
            "spindle_rpm": self.spindle_rpm,
            "feed_work": self.feed_work,
            "feed_travel": self.feed_travel,
            "z_safe": self.z_safe,
            "operations": [op.to_dict() for op in self.operations],
        }


def _parse_number(raw: str, what: str, line: int) -> float:
    """Liczba z kropką lub przecinkiem dziesiętnym (pliki z Excela)."""
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        raise ProgramError(f"niepoprawna liczba w polu {what}: '{raw.strip()}'", line)


def _parse_optional_number(raw: str, what: str, line: int) -> float | None:
    if raw.strip() == "":
        return None
    return _parse_number(raw, what, line)


def _parse_positive(raw: str, what: str, line: int) -> float | None:
    value = _parse_optional_number(raw, what, line)
    if value is not None and value <= 0:
        raise ProgramError(f"{what} musi być większe od zera, jest: {_fmt(value)}", line)
    return value


def _parse_positive_int(raw: str, what: str, line: int) -> int | None:
    if raw.strip() == "":
        return None
    value = _parse_number(raw, what, line)
    if value != int(value) or value < 1:
        raise ProgramError(
            f"{what} musi być liczbą całkowitą nie mniejszą niż 1, jest: '{raw.strip()}'",
            line,
        )
    return int(value)


def parse_program(text: str, expected_number: str | None = None) -> Program:
    """Parsuje treść pliku .prg; rzuca ProgramError z numerem linii."""
    header: dict[str, str] = {}
    header_lines: dict[str, int] = {}
    operations: list[Operation] = []
    section = None
    ops_header_seen = False
    ops_header = OPERATIONS_HEADER_V1
    ops_header_line: int | None = None

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper() == "[NAGLOWEK]":
            section = "header"
            continue
        if line.upper() == "[OPERACJE]":
            section = "operations"
            continue
        if section is None:
            raise ProgramError(
                "treść poza sekcją — plik musi zaczynać się od [NAGLOWEK]", line_no
            )

        if section == "header":
            if ";" not in line:
                raise ProgramError("oczekiwano pary KLUCZ;WARTOSC", line_no)
            key, _, value = line.partition(";")
            key = key.strip().upper()
            header[key] = value.strip()
            header_lines[key] = line_no
            continue

        # sekcja [OPERACJE]
        cells = [c.strip() for c in line.split(";")]
        if not ops_header_seen:
            upper = [c.upper() for c in cells]
            match = [h for h in SUPPORTED_FORMATS.values() if upper == h]
            if match:
                ops_header = match[0]
            else:
                raise ProgramError(
                    "pierwsza linia sekcji [OPERACJE] musi być nagłówkiem jednego "
                    "z obsługiwanych formatów: "
                    + " | ".join(
                        f"format {v}: " + ";".join(h)
                        for v, h in sorted(SUPPORTED_FORMATS.items())
                    ),
                    line_no,
                )
            ops_header_seen = True
            ops_header_line = line_no
            continue

        # dopełnij brakujące puste kolumny na końcu (Excel potrafi je uciąć)
        while len(cells) < len(ops_header):
            cells.append("")
        if len(cells) > len(ops_header):
            raise ProgramError(
                f"za dużo kolumn ({len(cells)}), oczekiwano {len(ops_header)}",
                line_no,
            )

        if ops_header is OPERATIONS_HEADER_V1:
            lp_raw, op_type_raw, x, y, z, x2, y2, note = cells
            feed_raw = rpm_raw = passes_raw = step_raw = torque_raw = ""
            smart_raw = ""
        elif ops_header is OPERATIONS_HEADER_V2:
            (
                lp_raw, op_type_raw, x, y, z, x2, y2,
                feed_raw, passes_raw, step_raw, note,
            ) = cells
            rpm_raw = torque_raw = smart_raw = ""
        elif ops_header is OPERATIONS_HEADER_V3:
            (
                lp_raw, op_type_raw, x, y, z, x2, y2,
                feed_raw, rpm_raw, passes_raw, step_raw, note,
            ) = cells
            torque_raw = smart_raw = ""
        elif ops_header is OPERATIONS_HEADER_V4:
            (
                lp_raw, op_type_raw, x, y, z, x2, y2,
                feed_raw, rpm_raw, torque_raw, passes_raw, step_raw, note,
            ) = cells
            smart_raw = ""
        else:
            (
                lp_raw, op_type_raw, x, y, z, x2, y2,
                feed_raw, rpm_raw, torque_raw, passes_raw, step_raw,
                smart_raw, note,
            ) = cells
        try:
            lp = int(lp_raw)
        except ValueError:
            raise ProgramError(f"niepoprawny numer LP: '{lp_raw}'", line_no)

        op_type = op_type_raw.upper()
        if op_type not in OPERATION_TYPES:
            raise ProgramError(
                f"nieznana operacja '{op_type_raw}' — dozwolone: "
                + ", ".join(OPERATION_TYPES),
                line_no,
            )

        op = Operation(
            lp=lp,
            op_type=op_type,
            x=_parse_optional_number(x, "X", line_no),
            y=_parse_optional_number(y, "Y", line_no),
            z=_parse_optional_number(z, "Z", line_no),
            x2=_parse_optional_number(x2, "X2", line_no),
            y2=_parse_optional_number(y2, "Y2", line_no),
            feed=_parse_positive(feed_raw, "POSUW", line_no),
            rpm=_parse_optional_number(rpm_raw, "OBROTY", line_no),
            passes=_parse_positive_int(passes_raw, "PRZEJSCIA", line_no),
            depth_step=_parse_positive(step_raw, "PRZYROST", line_no),
            torque_pct=_parse_optional_number(torque_raw, "MOMENT", line_no),
            smart=smart_raw.strip(),
            note=note,
        )

        if op.rpm is not None and op.rpm < 0:
            raise ProgramError("OBROTY nie mogą być ujemne (0 = wyłącz wrzeciono)", line_no)
        if op.torque_pct is not None and not (0 < op.torque_pct <= 100):
            raise ProgramError(
                f"MOMENT musi mieścić się w przedziale (0, 100] %, jest "
                f"{_fmt(op.torque_pct)}",
                line_no,
            )
        if op.passes is not None and op.depth_step is not None:
            raise ProgramError(
                "wypełnij PRZEJSCIA albo PRZYROST, nie oba naraz "
                "(liczba przejść albo przyrost na przejście)",
                line_no,
            )
        if op_type not in CUTTING_TYPES and (
            op.passes is not None or op.depth_step is not None
        ):
            raise ProgramError(
                f"operacja {op_type} nie przyjmuje PRZEJSCIA ani PRZYROST "
                "— to parametry operacji skrawających",
                line_no,
            )
        if op_type in ("PAUZA", "WRZECIONO", "SMART") and op.feed is not None:
            raise ProgramError(
                f"operacja {op_type} nie przyjmuje POSUW"
                + (
                    " — prędkości są w definicji SMART"
                    if op_type == "SMART"
                    else ""
                ),
                line_no,
            )
        if op_type in ("PAUZA", "WRZECIONO") and op.torque_pct is not None:
            raise ProgramError(
                f"operacja {op_type} nie przyjmuje MOMENT — nie porusza osiami", line_no
            )
        if op_type == "SMART" and op.torque_pct is not None:
            raise ProgramError(
                "operacja SMART nie przyjmuje MOMENT — próg siły jest "
                "parametrem definicji SMART, nie kolumną programu",
                line_no,
            )
        if op_type == "SMART" and any(
            v is not None for v in (op.x, op.y, op.z, op.x2, op.y2)
        ):
            raise ProgramError(
                "operacja SMART nie przyjmuje współrzędnych — jedzie od miejsca, "
                "w którym stoi maszyna, o dystans z definicji SMART",
                line_no,
            )
        if op_type != "SMART" and op.smart:
            raise ProgramError(
                f"kolumna SMART dotyczy wyłącznie operacji SMART, a jest przy "
                f"{op_type}",
                line_no,
            )
        if op_type == "SMART" and op.smart and not is_valid_name(op.smart):
            raise ProgramError(
                f"nieprawidłowa nazwa definicji SMART '{op.smart}' — zacznij od "
                "litery, dalej litery, cyfry, podkreślenie albo myślnik",
                line_no,
            )
        if op_type != "WRZECIONO" and op.rpm is not None:
            raise ProgramError(
                "kolumna OBROTY dotyczy wyłącznie operacji WRZECIONO", line_no
            )

        required = OPERATION_TYPES[op_type]
        values = {
            "X": op.x, "Y": op.y, "Z": op.z, "X2": op.x2, "Y2": op.y2,
            "OBROTY": op.rpm, "SMART": op.smart or None,
        }
        for col in required:
            if values[col] is None:
                raise ProgramError(
                    f"operacja {op_type} wymaga wypełnionej kolumny {col}", line_no
                )
        operations.append(op)

    if not ops_header_seen:
        raise ProgramError("brak sekcji [OPERACJE]")

    for key in REQUIRED_HEADER_KEYS:
        if key not in header or header[key] == "":
            raise ProgramError(f"brak wymaganego pola nagłówka: {key}")

    format_raw = header["FORMAT"].strip()
    try:
        format_version = int(format_raw)
    except ValueError:
        format_version = -1
    if format_version not in SUPPORTED_FORMATS:
        raise ProgramError(
            f"nieobsługiwana wersja formatu: {format_raw} (obsługiwane: "
            + ", ".join(str(v) for v in sorted(SUPPORTED_FORMATS))
            + ")",
            header_lines.get("FORMAT"),
        )
    if SUPPORTED_FORMATS[format_version] is not ops_header:
        expected = len(SUPPORTED_FORMATS[format_version])
        raise ProgramError(
            f"nagłówek sekcji [OPERACJE] nie pasuje do FORMAT;{format_version} — "
            f"ten format ma {expected} kolumn: "
            + ";".join(SUPPORTED_FORMATS[format_version]),
            ops_header_line,
        )

    number = header["PROGRAM"].strip()
    if not NC12_RE.match(number):
        raise ProgramError(
            f"numer programu musi mieć dokładnie 12 cyfr, jest: '{number}'",
            header_lines.get("PROGRAM"),
        )
    if expected_number and number != expected_number:
        raise ProgramError(
            f"numer PROGRAM ({number}) nie zgadza się z nazwą pliku "
            f"({expected_number})",
            header_lines.get("PROGRAM"),
        )

    if not operations:
        raise ProgramError("program nie zawiera żadnych operacji")

    for i, op in enumerate(operations, start=1):
        if op.lp != i:
            raise ProgramError(
                f"numeracja LP musi być ciągła od 1 — oczekiwano {i}, jest {op.lp}"
            )

    def header_num(key: str) -> float:
        return _parse_number(header[key], key, header_lines.get(key, 0))

    return Program(
        number=number,
        name=header["NAZWA"],
        material=header.get("MATERIAL", ""),
        author=header.get("AUTOR", ""),
        date=header.get("DATA", ""),
        spindle_rpm=header_num("OBROTY_FREZU"),
        feed_work=header_num("POSUW_ROBOCZY"),
        feed_travel=header_num("POSUW_DOJAZDU"),
        z_safe=header_num("Z_BEZPIECZNE"),
        operations=operations,
    )


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def serialize_program(program: Program) -> str:
    """Zapisuje program do tekstu w formacie .prg (format 5)."""
    lines = [
        "[NAGLOWEK]",
        "FORMAT;5",
        f"PROGRAM;{program.number}",
        f"NAZWA;{program.name}",
    ]
    if program.material:
        lines.append(f"MATERIAL;{program.material}")
    if program.author:
        lines.append(f"AUTOR;{program.author}")
    if program.date:
        lines.append(f"DATA;{program.date}")
    lines += [
        f"OBROTY_FREZU;{_fmt(program.spindle_rpm)}",
        f"POSUW_ROBOCZY;{_fmt(program.feed_work)}",
        f"POSUW_DOJAZDU;{_fmt(program.feed_travel)}",
        f"Z_BEZPIECZNE;{_fmt(program.z_safe)}",
        "",
        "[OPERACJE]",
        ";".join(OPERATIONS_HEADER),
    ]
    for op in program.operations:
        lines.append(
            ";".join(
                [
                    str(op.lp),
                    op.op_type,
                    _fmt(op.x),
                    _fmt(op.y),
                    _fmt(op.z),
                    _fmt(op.x2),
                    _fmt(op.y2),
                    _fmt(op.feed),
                    _fmt(op.rpm),
                    _fmt(op.torque_pct),
                    "" if op.passes is None else str(op.passes),
                    _fmt(op.depth_step),
                    op.smart,
                    op.note.replace(";", ","),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def smart_warnings(program: Program, known_names) -> list[str]:
    """Operacje SMART wskazujące definicję, której nie ma w konfiguracji.

    Świadomie ostrzeżenie, a nie błąd parsera: plik `.prg` jest samodzielny
    i może trafić na maszynę wcześniej niż definicja. Program da się otworzyć
    i poprawić, a start i tak przerwie się czytelnym błędem maszyny.
    """
    known = set(known_names)
    out: list[str] = []
    for op in program.operations:
        if op.op_type == "SMART" and op.smart not in known:
            out.append(
                f"operacja LP={op.lp}: nie ma definicji SMART '{op.smart}' — "
                "program uruchomi się dopiero po jej dodaniu na ekranie "
                "„Funkcje SMART”"
            )
    return out


def pass_depths(op: Operation, surface: float = 0.0) -> list[float]:
    """Kolejne głębokości Z dla operacji — ostatnia zawsze równa zadanej.

    Głębokość dzielona jest od powierzchni materiału (domyślnie Z=0) do Z
    z operacji. Technolog podaje albo liczbę przejść (PRZEJSCIA), albo
    przyrost na przejście (PRZYROST); bez żadnego z nich jest jedno przejście.
    """
    if op.z is None:
        return []
    total = op.z - surface
    if op.passes:
        count = op.passes
    elif op.depth_step:
        count = max(1, math.ceil(abs(total) / op.depth_step - 1e-9))
    else:
        count = 1
    return [surface + total * (k + 1) / count for k in range(count)]


def cut_path(op: Operation) -> list[tuple[float, float]]:
    """Punkty XY, przez które przechodzi narzędzie na danej głębokości.

    Zaczyna się zawsze w (X, Y), więc lista zawiera tylko kolejne punkty.
    PUNKT nie ma żadnych — to samo zagłębienie w miejscu.
    """
    if op.op_type == "LINIA":
        return [(op.x2, op.y2)]
    if op.op_type == "PROSTOKAT":
        # obrys po narożnikach przeciwległych, z powrotem do punktu startu
        return [(op.x2, op.y), (op.x2, op.y2), (op.x, op.y2), (op.x, op.y)]
    return []


def validate_work_area(
    program: Program,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> None:
    """Sprawdza, czy wszystkie punkty programu mieszczą się w obszarze roboczym."""
    if not (z_min <= program.z_safe <= z_max):
        raise ProgramError(
            f"Z_BEZPIECZNE={_fmt(program.z_safe)} poza zakresem osi Z "
            f"({_fmt(z_min)}..{_fmt(z_max)})"
        )
    for op in program.operations:
        points = []
        if op.x is not None and op.y is not None:
            points.append((op.x, op.y))
        if op.x2 is not None and op.y2 is not None:
            points.append((op.x2, op.y2))
        # narożniki prostokąta, których nie ma wprost w kolumnach
        if op.op_type == "PROSTOKAT":
            points += [(op.x2, op.y), (op.x, op.y2)]
        for px, py in points:
            if not (x_min <= px <= x_max) or not (y_min <= py <= y_max):
                raise ProgramError(
                    f"operacja LP={op.lp}: punkt ({_fmt(px)}, {_fmt(py)}) poza "
                    f"obszarem roboczym X {_fmt(x_min)}..{_fmt(x_max)}, "
                    f"Y {_fmt(y_min)}..{_fmt(y_max)}"
                )
        if op.z is not None and not (z_min <= op.z <= z_max):
            raise ProgramError(
                f"operacja LP={op.lp}: Z={_fmt(op.z)} poza zakresem "
                f"{_fmt(z_min)}..{_fmt(z_max)}"
            )
