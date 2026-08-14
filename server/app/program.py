"""Parser i serializator plików programu (.prg) — format 1.

Format opisany w docs/FORMAT_PROGRAMU.md: sekcja [NAGLOWEK] z parami
KLUCZ;WARTOSC oraz sekcja [OPERACJE] z tabelą rozdzielaną średnikami.
Komunikaty błędów po polsku, z numerem linii — trafiają wprost do
technologa/operatora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NC12_RE = re.compile(r"^\d{12}$")

OPERATIONS_HEADER = ["LP", "OPERACJA", "X", "Y", "Z", "X2", "Y2", "UWAGI"]

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

# rodzaj operacji -> kolumny współrzędnych, które muszą być wypełnione
OPERATION_TYPES = {
    "PUNKT": ["X", "Y", "Z"],
    "LINIA": ["X", "Y", "Z", "X2", "Y2"],
    "PAUZA": [],
}


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


def parse_program(text: str, expected_number: str | None = None) -> Program:
    """Parsuje treść pliku .prg; rzuca ProgramError z numerem linii."""
    header: dict[str, str] = {}
    header_lines: dict[str, int] = {}
    operations: list[Operation] = []
    section = None
    ops_header_seen = False

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
            if [c.upper() for c in cells] != OPERATIONS_HEADER:
                raise ProgramError(
                    "pierwsza linia sekcji [OPERACJE] musi być nagłówkiem: "
                    + ";".join(OPERATIONS_HEADER),
                    line_no,
                )
            ops_header_seen = True
            continue

        # dopełnij brakujące puste kolumny na końcu (Excel potrafi je uciąć)
        while len(cells) < len(OPERATIONS_HEADER):
            cells.append("")
        if len(cells) > len(OPERATIONS_HEADER):
            raise ProgramError(
                f"za dużo kolumn ({len(cells)}), oczekiwano {len(OPERATIONS_HEADER)}",
                line_no,
            )

        lp_raw, op_type_raw, x, y, z, x2, y2, note = cells
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
            note=note,
        )

        required = OPERATION_TYPES[op_type]
        values = {"X": op.x, "Y": op.y, "Z": op.z, "X2": op.x2, "Y2": op.y2}
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

    if header["FORMAT"].strip() != "1":
        raise ProgramError(
            f"nieobsługiwana wersja formatu: {header['FORMAT']} (obsługiwana: 1)",
            header_lines.get("FORMAT"),
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
    """Zapisuje program do tekstu w formacie .prg (format 1)."""
    lines = [
        "[NAGLOWEK]",
        "FORMAT;1",
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
                    op.note.replace(";", ","),
                ]
            )
        )
    return "\n".join(lines) + "\n"


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
