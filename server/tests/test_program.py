"""Testy parsera i walidacji plików programu (.prg)."""

import pytest

from app.program import (
    Program,
    ProgramError,
    parse_program,
    serialize_program,
    validate_work_area,
)

VALID = """\
# komentarz
[NAGLOWEK]
FORMAT;1
PROGRAM;583912004711
NAZWA;Plytka testowa
MATERIAL;PMMA
OBROTY_FREZU;12000
POSUW_ROBOCZY;300
POSUW_DOJAZDU;3000
Z_BEZPIECZNE;10.0

[OPERACJE]
LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI
1;PUNKT;12.500;30.000;-1.50;;;wlewek gorny
2;LINIA;40.000;10.000;-1.50;55.000;10.000;wlewek boczny
3;PAUZA;;;;;;kontrola
"""


def test_parse_valid_program():
    p = parse_program(VALID, expected_number="583912004711")
    assert p.number == "583912004711"
    assert p.name == "Plytka testowa"
    assert p.spindle_rpm == 12000
    assert len(p.operations) == 3
    assert p.operations[0].op_type == "PUNKT"
    assert p.operations[1].x2 == 55.0
    assert p.operations[2].op_type == "PAUZA"


def test_comma_decimal_separator_accepted():
    """Pliki zapisane z Excela w polskich ustawieniach używają przecinka."""
    text = VALID.replace("12.500", "12,500")
    p = parse_program(text)
    assert p.operations[0].x == 12.5


def test_roundtrip_serialize_parse():
    p = parse_program(VALID)
    text = serialize_program(p)
    p2 = parse_program(text, expected_number=p.number)
    assert p2.to_dict() == p.to_dict()


def test_number_mismatch_with_filename():
    with pytest.raises(ProgramError, match="nie zgadza się"):
        parse_program(VALID, expected_number="000000000000")


def test_invalid_program_number():
    text = VALID.replace("PROGRAM;583912004711", "PROGRAM;123")
    with pytest.raises(ProgramError, match="12 cyfr"):
        parse_program(text)


def test_missing_required_header_key():
    text = VALID.replace("OBROTY_FREZU;12000\n", "")
    with pytest.raises(ProgramError, match="OBROTY_FREZU"):
        parse_program(text)


def test_unknown_operation():
    text = VALID.replace("1;PUNKT", "1;WIERC")
    with pytest.raises(ProgramError, match="nieznana operacja"):
        parse_program(text)


def test_linia_requires_x2_y2():
    text = VALID.replace(
        "2;LINIA;40.000;10.000;-1.50;55.000;10.000;wlewek boczny",
        "2;LINIA;40.000;10.000;-1.50;;;wlewek boczny",
    )
    with pytest.raises(ProgramError, match="X2"):
        parse_program(text)


def test_lp_must_be_sequential():
    text = VALID.replace("3;PAUZA", "5;PAUZA")
    with pytest.raises(ProgramError, match="LP"):
        parse_program(text)


def test_error_reports_line_number():
    text = VALID.replace("1;PUNKT;12.500", "1;PUNKT;abc")
    with pytest.raises(ProgramError) as exc:
        parse_program(text)
    assert "linia" in str(exc.value)


def test_work_area_validation():
    p = parse_program(VALID)
    validate_work_area(p, x_min=-100, x_max=100, y_min=-100, y_max=100, z_min=-20, z_max=50)
    with pytest.raises(ProgramError, match="poza obszarem"):
        validate_work_area(p, x_min=0, x_max=20, y_min=-100, y_max=100, z_min=-20, z_max=50)


def test_empty_operations_rejected():
    text = VALID.split("[OPERACJE]")[0] + "[OPERACJE]\nLP;OPERACJA;X;Y;Z;X2;Y2;UWAGI\n"
    with pytest.raises(ProgramError, match="żadnych operacji"):
        parse_program(text)
