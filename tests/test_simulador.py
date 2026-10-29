import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulador as sim


def test_determinista_con_misma_semilla():
    assert sim.simular(42) == sim.simular(42)


def test_semilla_distinta_cambia_resultado():
    assert sim.simular(42) != sim.simular(7)


def test_numero_de_filas():
    assert len(sim.simular(42)) == 12 * 4 * 2  # 12 días x 4 iteraciones x 2 campañas


def test_no_excede_presupuesto():
    r = sim.resumen(sim.simular(42))
    assert all(v["gasto"] <= 500.01 for v in r.values())


def test_conversiones_en_rango_del_sensor():
    assert all(0 <= f["conversiones"] <= 10 for f in sim.simular(42))


def test_ctr_en_rango_del_sensor():
    assert all(0 <= f["ctr"] <= 0.05 for f in sim.simular(42))


def test_periodos():
    assert sim.periodo_de(date(2026, 11, 9)) == "dia_laboral"      # lunes
    assert sim.periodo_de(date(2026, 11, 13)) == "fin_de_semana"   # viernes
    assert sim.periodo_de(date(2026, 12, 7)) == "temporada_alta"   # diciembre
    assert sim.periodo_de(date(2026, 11, 9), {"2026-11-09"}) == "eventos_especiales"
