"""Wyjścia cyfrowe: komenda do mostka, przeznaczenie, gaszenie przy STOP.

Do tej pory krok WYJSCIE zmieniał tylko liczbę w statusie — mostek nie miał
komendy ustawienia wyjścia. Te testy pilnują, że teraz faktycznie idzie
komenda do sterownika i że nie da się jej wysłać na wyjście wrzeciona.
"""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import cycle as cycle_mod  # noqa: E402
from app import outputs as outputs_mod  # noqa: E402
from app.machine import MachineState, SC4HubMachine, SimulatedMachine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _cycle(*steps):
    return cycle_mod.parse_cycle({"name": "test", "steps": list(steps)})


def _output_step(lp, name, on):
    return {"lp": lp, "kind": "WYJSCIE", "output": name, "output_on": on}


# --- mapowanie na fizyczne wyjścia ----------------------------------------


def test_nazwy_logiczne_mapuja_sie_na_wyjscia_huba():
    assert cycle_mod.output_index("wyjscie_0") == 0
    assert cycle_mod.output_index("wyjscie_1") == 1


def test_nieznane_wyjscie_jest_odrzucane():
    with pytest.raises(cycle_mod.CycleError, match="nieznane wyjście"):
        cycle_mod.output_index("wyjscie_7")


def test_wiadomo_ktore_wyjscia_wykorzystuje_cykl():
    cyc = _cycle(_output_step(1, "wyjscie_1", True), _output_step(2, "wyjscie_1", False))
    assert cycle_mod.outputs_used(cyc) == {"wyjscie_1"}


# --- komenda do mostka ----------------------------------------------------


def _bridge(cycle_def, outputs_cfg=None):
    m = SC4HubMachine("127.0.0.1", 8500)
    calls = []

    async def fake_command(command: str) -> str:
        calls.append(command)
        return "OK"

    m._command = fake_command
    m.calls = calls
    m.apply_cycle(cycle_def)
    if outputs_cfg is not None:
        m.apply_output_config(outputs_cfg)
    m.status.state = MachineState.READY
    return m


async def _run_cycle(machine):
    await machine.start_cycle()
    task = machine._run_task
    if task is not None:
        await task


def test_krok_wyjscie_wysyla_komende_do_mostka():
    """Sedno zmiany: WYJSCIE przełącza teraz fizyczne wyjście huba."""
    m = _bridge(_cycle(_output_step(1, "wyjscie_1", True)))
    asyncio.run(_run_cycle(m))
    assert "OUTPUT 1 1" in m.calls


def test_wylaczenie_wyjscia_tez_idzie_do_mostka():
    m = _bridge(_cycle(_output_step(1, "wyjscie_0", False)))
    asyncio.run(_run_cycle(m))
    assert "OUTPUT 0 0" in m.calls


def test_status_odzwierciedla_wyjscie_dopiero_po_potwierdzeniu():
    """Odmowa sterownika nie może zostawić na ekranie załączonego podajnika."""

    async def scenario():
        m = _bridge(_cycle(_output_step(1, "wyjscie_1", True)))

        async def odmowa(command: str) -> str:
            from app.machine import MachineError

            raise MachineError("sterownik odrzucił komendę")

        m._command = odmowa
        await _run_cycle(m)
        return m

    m = asyncio.run(scenario())
    assert m.status.outputs["wyjscie_1"] is False
    assert m.status.state is MachineState.ALARM


def test_status_z_mostka_czyta_stan_wyjsc():
    m = SC4HubMachine("127.0.0.1", 8500)

    async def fake_command(command: str) -> str:
        return "OK STATE=READY EN=1 X=0.000 Y=0.000 Z=0.000 SP=0 REL=- OUT=01"

    m._command = fake_command
    asyncio.run(m.poll_status())
    assert m.status.outputs == {"wyjscie_0": False, "wyjscie_1": True}


def test_starszy_mostek_bez_pola_out_nie_zeruje_stanu():
    """Mostek sprzed tej zmiany nie wysyła OUT= — nie udajemy, że wie."""
    m = SC4HubMachine("127.0.0.1", 8500)
    m.status.outputs["wyjscie_1"] = True

    async def fake_command(command: str) -> str:
        return "OK STATE=READY EN=1 X=0.000 Y=0.000 Z=0.000 SP=0 REL=-"

    m._command = fake_command
    asyncio.run(m.poll_status())
    assert m.status.outputs["wyjscie_1"] is True


# --- przeznaczenie wyjść --------------------------------------------------


def test_domyslnie_wyjscia_sa_nieuzywane():
    cfg = outputs_mod.default_outputs()
    assert all(c.purpose == outputs_mod.PURPOSE_NONE for c in cfg.values())
    assert all(c.off_on_stop is False for c in cfg.values())


def test_wyrzutnik_domyslnie_gasnie_przy_stop():
    cfg = outputs_mod.parse_outputs({"wyjscie_1": {"purpose": "wyrzutnik"}})
    assert cfg["wyjscie_1"].off_on_stop is True


def test_docisk_domyslnie_nie_gasnie_przy_stop():
    """Zdjęcie docisku przy STOP potrafi upuścić detal — to musi być decyzją."""
    cfg = outputs_mod.parse_outputs({"wyjscie_1": {"purpose": "docisk"}})
    assert cfg["wyjscie_1"].off_on_stop is False


def test_jawne_ustawienie_ma_pierwszenstwo_nad_domyslnym():
    cfg = outputs_mod.parse_outputs(
        {"wyjscie_1": {"purpose": "wyrzutnik", "off_on_stop": False}}
    )
    assert cfg["wyjscie_1"].off_on_stop is False


def test_nieznane_przeznaczenie_jest_odrzucane():
    with pytest.raises(outputs_mod.OutputConfigError, match="przeznaczenie"):
        outputs_mod.parse_outputs({"wyjscie_0": {"purpose": "kawa"}})


def test_nieznane_wyjscie_w_konfiguracji_jest_odrzucane():
    with pytest.raises(outputs_mod.OutputConfigError, match="nieznane wyjścia"):
        outputs_mod.parse_outputs({"wyjscie_9": {"purpose": "lampka"}})


def test_etykieta_zastepuje_nazwe_techniczna():
    cfg = outputs_mod.parse_outputs(
        {"wyjscie_0": {"purpose": "podajnik", "label": "podajnik detali"}}
    )
    assert cfg["wyjscie_0"].display("wyjscie_0") == "podajnik detali"
    assert outputs_mod.OutputConfig().display("wyjscie_1") == "wyjscie_1"


# --- ostrzeżenia ----------------------------------------------------------


def test_ostrzezenie_o_konflikcie_z_wyjsciem_wrzeciona():
    warns = outputs_mod.warnings(
        outputs_mod.default_outputs(), {"wyjscie_0"}, False, "brake0"
    )
    assert any("zajęte przez wrzeciono" in w or "wrzeciona" in w for w in warns)


def test_brak_ostrzezenia_gdy_cykl_uzywa_wolnego_wyjscia():
    cfg = outputs_mod.parse_outputs({"wyjscie_1": {"purpose": "wyrzutnik"}})
    warns = outputs_mod.warnings(cfg, {"wyjscie_1"}, False, "brake0")
    assert not any("wrzeciona" in w for w in warns)


def test_ostrzezenie_o_wyjsciu_ktorego_nikt_nie_zalacza():
    cfg = outputs_mod.parse_outputs({"wyjscie_1": {"purpose": "lampka"}})
    warns = outputs_mod.warnings(cfg, set(), False, None)
    assert any("żaden" in w for w in warns)


def test_ostrzezenia_sprzetowe_o_zasilaniu_i_obciazalnosci():
    warns = outputs_mod.warnings(outputs_mod.default_outputs(), set(), True, None)
    assert any("24 V" in w for w in warns)
    assert any("500 mA" in w for w in warns)


# --- gaszenie przy STOP ---------------------------------------------------


def test_gasimy_tylko_wyjscia_oznaczone_do_gaszenia():
    m = SimulatedMachine()
    m.apply_output_config(
        outputs_mod.parse_outputs(
            {
                "wyjscie_0": {"purpose": "docisk"},          # off_on_stop = nie
                "wyjscie_1": {"purpose": "wyrzutnik"},        # off_on_stop = tak
            }
        )
    )
    m.status.outputs["wyjscie_0"] = True
    m.status.outputs["wyjscie_1"] = True
    assert m.outputs_to_clear() == ["wyjscie_1"]


def test_mostek_gasi_wyjscie_po_zakonczeniu_cyklu():
    cfg = outputs_mod.parse_outputs({"wyjscie_1": {"purpose": "wyrzutnik"}})
    m = _bridge(_cycle(_output_step(1, "wyjscie_1", True)), cfg)
    asyncio.run(_run_cycle(m))
    assert m.calls[-1] == "OUTPUT 1 0"
    assert m.status.outputs["wyjscie_1"] is False


def test_mostek_zostawia_wyjscie_nieoznaczone_do_gaszenia():
    cfg = outputs_mod.parse_outputs({"wyjscie_1": {"purpose": "docisk"}})
    m = _bridge(_cycle(_output_step(1, "wyjscie_1", True)), cfg)
    asyncio.run(_run_cycle(m))
    assert not any(c == "OUTPUT 1 0" for c in m.calls)
    assert m.status.outputs["wyjscie_1"] is True


# --- API ------------------------------------------------------------------


def test_api_outputs_odczyt(client):
    data = client.get("/api/outputs").json()
    assert set(data["outputs"]) == set(cycle_mod.OUTPUT_NAMES)
    assert "podajnik" in data["purposes"]


def test_api_outputs_zapis(client):
    res = client.put(
        "/api/outputs",
        json={"outputs": {"wyjscie_1": {"purpose": "wyrzutnik", "label": "wyrzutnik detali"}}},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outputs"]["wyjscie_1"]["purpose"] == "wyrzutnik"
    assert body["outputs"]["wyjscie_1"]["off_on_stop"] is True
    # sprzątamy — inne testy zakładają wartości domyślne
    client.put("/api/outputs", json={"outputs": {"wyjscie_1": {"purpose": "nieuzywane"}}})


def test_api_outputs_odrzuca_bledne_przeznaczenie(client):
    res = client.put("/api/outputs", json={"outputs": {"wyjscie_0": {"purpose": "kawa"}}})
    assert res.status_code == 422
