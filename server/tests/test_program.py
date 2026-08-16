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


# --- format 2: parametry operacji ----------------------------------------

from app.program import pass_depths  # noqa: E402

FORMAT2 = """[NAGLOWEK]
FORMAT;2
PROGRAM;583912004711
NAZWA;Test formatu 2
OBROTY_FREZU;12000
POSUW_ROBOCZY;300
POSUW_DOJAZDU;3000
Z_BEZPIECZNE;10

[OPERACJE]
LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;PRZEJSCIA;PRZYROST;UWAGI
1;PUNKT;10;20;-2;;;150;3;;trzy przejscia
2;LINIA;0;0;-1.5;10;0;;;0.5;przyrost 0.5
3;PUNKT;5;5;-1;;;;;;domyslne
"""


def test_parse_format_2():
    p = parse_program(FORMAT2, "583912004711")
    assert p.operations[0].feed == 150
    assert p.operations[0].passes == 3
    assert p.operations[0].depth_step is None
    assert p.operations[1].depth_step == 0.5
    assert p.operations[2].feed is None


def test_format_1_still_parses_and_upgrades_on_save():
    p = parse_program(VALID)
    assert p.operations[0].passes is None
    text = serialize_program(p)
    assert "FORMAT;3" in text
    assert "POSUW;OBROTY;PRZEJSCIA;PRZYROST" in text
    again = parse_program(text)
    assert len(again.operations) == len(p.operations)


def test_format_and_header_must_match():
    bad = FORMAT2.replace("FORMAT;2", "FORMAT;1")
    with pytest.raises(ProgramError) as e:
        parse_program(bad, "583912004711")
    assert "FORMAT;1" in str(e.value)


def test_passes_and_step_are_exclusive():
    bad = FORMAT2.replace("150;3;;trzy przejscia", "150;3;0.5;oba naraz")
    with pytest.raises(ProgramError) as e:
        parse_program(bad, "583912004711")
    assert "nie oba naraz" in str(e.value)


def test_pause_rejects_operation_parameters():
    bad = FORMAT2.replace("3;PUNKT;5;5;-1;;;;;;domyslne", "3;PAUZA;;;;;;;2;;zle")
    with pytest.raises(ProgramError):
        parse_program(bad, "583912004711")


def test_invalid_parameter_values():
    for cell, msg in [("150;0;;x", "PRZEJSCIA"), ("-5;3;;x", "POSUW"), ("150;2.5;;x", "PRZEJSCIA")]:
        bad = FORMAT2.replace("150;3;;trzy przejscia", cell)
        with pytest.raises(ProgramError) as e:
            parse_program(bad, "583912004711")
        assert msg in str(e.value)


def test_pass_depths_by_count():
    p = parse_program(FORMAT2, "583912004711")
    assert pass_depths(p.operations[0]) == [-2 / 3 * 1, -2 / 3 * 2, -2.0]


def test_pass_depths_by_step():
    p = parse_program(FORMAT2, "583912004711")
    depths = pass_depths(p.operations[1])   # Z=-1.5, przyrost 0.5
    assert len(depths) == 3
    assert depths[-1] == -1.5


def test_pass_depths_default_single():
    p = parse_program(FORMAT2, "583912004711")
    assert pass_depths(p.operations[2]) == [-1.0]


# --- format 3: nowe rodzaje operacji --------------------------------------

from app.program import cut_path  # noqa: E402

FORMAT3 = """[NAGLOWEK]
FORMAT;3
PROGRAM;583912004711
NAZWA;Test formatu 3
OBROTY_FREZU;12000
POSUW_ROBOCZY;300
POSUW_DOJAZDU;3000
Z_BEZPIECZNE;10

[OPERACJE]
LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;PRZEJSCIA;PRZYROST;UWAGI
1;WRZECIONO;;;;;;;8000;;;zwolnij wrzeciono
2;SZYBKI;20;10;;;;;;;;przejazd
3;PROSTOKAT;0;0;-1;10;5;;;2;;obrys
4;WRZECIONO;;;;;;;0;;;wylacz
"""


def test_parse_format_3_operations():
    p = parse_program(FORMAT3, "583912004711")
    assert [o.op_type for o in p.operations] == ["WRZECIONO", "SZYBKI", "PROSTOKAT", "WRZECIONO"]
    assert p.operations[0].rpm == 8000
    assert p.operations[2].passes == 2
    assert p.operations[3].rpm == 0


def test_rectangle_path_closes():
    p = parse_program(FORMAT3, "583912004711")
    rect = p.operations[2]
    assert cut_path(rect) == [(10, 0), (10, 5), (0, 5), (0, 0)]


def test_line_path_and_point_path():
    p = parse_program(FORMAT2, "583912004711")
    assert cut_path(p.operations[0]) == []            # PUNKT
    assert cut_path(p.operations[1]) == [(10, 0)]     # LINIA


def test_rpm_only_for_spindle_operation():
    bad = FORMAT3.replace("3;PROSTOKAT;0;0;-1;10;5;;;2;;obrys",
                          "3;PROSTOKAT;0;0;-1;10;5;;500;2;;obrys")
    with pytest.raises(ProgramError) as e:
        parse_program(bad, "583912004711")
    assert "OBROTY" in str(e.value)


def test_passes_rejected_on_non_cutting_operation():
    bad = FORMAT3.replace("2;SZYBKI;20;10;;;;;;;;przejazd",
                          "2;SZYBKI;20;10;;;;;;3;;przejazd")
    with pytest.raises(ProgramError) as e:
        parse_program(bad, "583912004711")
    assert "PRZEJSCIA" in str(e.value)


def test_spindle_operation_requires_rpm():
    bad = FORMAT3.replace("1;WRZECIONO;;;;;;;8000;;;zwolnij wrzeciono",
                          "1;WRZECIONO;;;;;;;;;;brak obrotow")
    with pytest.raises(ProgramError) as e:
        parse_program(bad, "583912004711")
    assert "OBROTY" in str(e.value)


def test_rectangle_corners_checked_against_work_area():
    p = parse_program(FORMAT3, "583912004711")
    # prostokąt 0,0..10,5 mieści się
    validate_work_area(p, -100, 100, -100, 100, -20, 50)
    # zawężony obszar: przeciwległy narożnik wypada poza
    with pytest.raises(ProgramError):
        validate_work_area(p, -100, 8, -100, 100, -20, 50)


def test_format_3_roundtrip():
    p = parse_program(FORMAT3, "583912004711")
    text = serialize_program(p)
    assert "FORMAT;3" in text
    again = parse_program(text, "583912004711")
    assert [o.op_type for o in again.operations] == [o.op_type for o in p.operations]
    assert again.operations[0].rpm == 8000
