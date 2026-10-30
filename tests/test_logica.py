import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import logica as L


def test_cpm_periodos():
    assert L.consultar_cpm("2026-11-09")["periodo"] == "dia_laboral"
    r = L.consultar_cpm("2026-11-13")
    assert r["periodo"] == "fin_de_semana" and r["variacion_vs_base"] == 0.20
    assert L.consultar_cpm("2026-12-07")["periodo"] == "temporada_alta"
    with pytest.raises(ValueError):
        L.consultar_cpm("09/11/2026")


def test_inventario_por_campana():
    assert [s["segment_id"] for s in L.inventario("Cultural")] == [1, 2, 5, 6, 7]
    assert [s["segment_id"] for s in L.inventario("romántica")] == [3, 4, 8, 9, 10]
    with pytest.raises(ValueError):
        L.inventario("Otra")


def test_metricas_por_defecto_hasta_corte():
    m = L.metricas("Cultural")
    assert m["hasta_iteracion"] == 24 and m["iteraciones_restantes"] == 24
    assert m["segmento_actual"]["segment_id"] == 1
    assert m["presupuesto_disponible"] == pytest.approx(250, abs=0.1)
    assert len(m["ultimas_iteraciones"]) == 4
    assert 0 <= m["estabilidad"] <= 1


def test_utilidad_acotada_y_monotona():
    bajo = L.utilidad("Cultural", 10, 0.5, 0.4)["utilidad"]
    alto = L.utilidad("Cultural", 20, 1.5, 0.8)["utilidad"]
    assert 0 <= bajo < alto <= 1
    assert L.utilidad("Cultural", 999, 99, 5)["utilidad"] == pytest.approx(1.0)
    # pesos distintos por campaña
    assert L.utilidad("Cultural", 24, 0, 0)["utilidad"] == pytest.approx(0.5)
    assert L.utilidad("Romantica", 24, 0, 0)["utilidad"] == pytest.approx(0.4)


def test_proyeccion_coherente():
    r = L.proyectar_escenario("Romantica", 3, 250)
    assert r["totales_12_dias"]["gasto"] == pytest.approx(500, abs=0.1)
    assert r["totales_12_dias"]["leads"] > 15
    # más presupuesto en el mismo segmento -> más leads
    mas = L.proyectar_escenario("Romantica", 3, 300)["totales_12_dias"]["leads"]
    assert mas > r["totales_12_dias"]["leads"]
    with pytest.raises(ValueError):
        L.proyectar_escenario("Romantica", 1, 250)  # segmento de otra campaña


def test_validar_accion():
    assert L.validar_accion("Cultural", 0.2, 0.1, 1)["valido"]
    assert not L.validar_accion("Cultural", 0.25)["valido"]
    assert not L.validar_accion("Cultural", cambio_puja_pct=-0.15)["valido"]
    assert not L.validar_accion("Cultural", cambios_audiencia=2)["valido"]
    assert not L.validar_accion("Cultural", pausar=True, roi_actual=1.2)["valido"]
    assert L.validar_accion("Cultural", pausar=True, roi_actual=0.3)["valido"]
    assert L.validar_accion("Cultural", roi_actual=0.3)["advertencias"]


def test_validar_reparto():
    # a las 24 iteraciones quedan ~250 por campaña
    ok = L.validar_reparto(200, 300.0032)
    assert ok["valido"], ok
    assert not L.validar_reparto(150, 350)["valido"]      # -40 %
    assert not L.validar_reparto(250, 300)["valido"]      # no conserva el total
