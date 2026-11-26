"""Guardrails deterministas y reglas del lazo Human-in-the-Loop (sin LLM ni red).

Los casos "reales" son las salidas que produjeron los agentes en la corrida final de la Fase 3
(logs/corrida.log.txt): deben pasar los guardrails. Los casos "maliciosos" simulan alucinaciones
típicas: segmentos inventados, repartos que no cuadran, auditorías incoherentes.
"""
import json
import re
from pathlib import Path

import pytest

import guardrails as g

LOG = Path(__file__).resolve().parents[1] / "logs" / "corrida.log.txt"


def _salidas_fase3() -> dict:
    """Extrae las 5 salidas completadas del log, en orden (T1, T2, T3, T4, T5)."""
    texto = LOG.read_text(encoding="utf-8")
    bloques = re.findall(r'agent="([^"]+)", status="completed", output="(.*?)"\n(?=\d{4}-\d{2}-\d{2} |\Z)', texto, flags=re.S)
    return {agente: salida for agente, salida in bloques}


@pytest.fixture(scope="module")
def fase3():
    s = _salidas_fase3()
    assert len(s) == 5, s.keys()
    return s


# --------------------------------------------------------------------------- extracción
def test_extraer_json_tolera_bloques_y_texto():
    assert g.extraer_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert g.extraer_json('Respuesta final: {"a": {"b": 2}} fin') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        g.extraer_json("sin json")
    with pytest.raises(ValueError):
        g.extraer_json("{roto: }")


def test_numero_acepta_formatos_comunes():
    assert g.numero("250.00 MXN", "x") == 250.0
    assert g.numero("$1,100", "x") == 1100.0
    with pytest.raises(ValueError):
        g.numero(True, "x")


# --------------------------------------------------------------------------- salidas reales
def test_salidas_reales_de_fase3_pasan_los_guardrails(fase3):
    gr = g.crear_guardrails(500.0)
    orden = [("Analista de Mercado de Meta Ads", "analisis"), ("Agente de Campaña Cultural", "cultural"),
             ("Agente de Campaña Romántica", "romantica"), ("Broker de Presupuesto", "asignacion"),
             ("Monitor Global de Cumplimiento", "auditoria")]
    for agente, clave in orden:
        ok, motivo = gr[clave](fase3[agente])
        assert ok, f"{clave}: {motivo}"
    assert gr["_estado"]["validacion_reparto"]["valido"]


# --------------------------------------------------------------------------- alucinaciones
def test_analista_no_puede_inventar_segmentos():
    obj = {"resumen_cpm": [], "observaciones": "",
           "cultural": {"segmentos_recomendados": [{"segment_id": 1}, {"segment_id": 99}]},
           "romantica": {"segmentos_recomendados": [{"segment_id": 3}, {"segment_id": 1}]}}
    errores = g.revisar_analisis(obj)
    assert any("99" in e for e in errores)
    assert any("Romantica" in e and "1" in e for e in errores)  # el 1 es de Cultural


def test_broker_debe_conservar_el_total():
    gr = g.crear_guardrails(500.0)
    malo = json.dumps({"presupuesto_cultural_mxn": 300, "presupuesto_romantica_mxn": 300,
                       "segmento_final": {"Cultural": 5, "Romantica": 3}, "justificacion": "",
                       "aclaraciones_solicitadas": [], "validacion": {}})
    ok, motivo = gr["asignacion"](malo)
    assert not ok and "conservar" in motivo


def test_broker_no_puede_exceder_20_por_ciento():
    errores, val = g.revisar_asignacion({"presupuesto_cultural_mxn": 350, "presupuesto_romantica_mxn": 150,
                                         "segmento_final": {}, "justificacion": "",
                                         "aclaraciones_solicitadas": [], "validacion": {}})
    assert not val["valido"] and any("20%" in e for e in errores)


def test_monitor_no_puede_declarar_cumplimiento_falso():
    gr = g.crear_guardrails(500.0)
    gr["asignacion"](json.dumps({"presupuesto_cultural_mxn": 400, "presupuesto_romantica_mxn": 100,
                                 "segmento_final": {}, "justificacion": "", "aclaraciones_solicitadas": [],
                                 "validacion": {}}))
    auditoria = json.dumps({"veredicto": "aprobado", "restricciones_cumplidas": True, "violaciones": [],
                            "objetivos": {}, "riesgos": [], "resumen_ejecutivo": ""})
    ok, motivo = gr["auditoria"](auditoria)
    assert not ok and "determinista" in motivo


def test_veredicto_fuera_de_catalogo():
    errores = g.revisar_auditoria({"veredicto": "excelente", "restricciones_cumplidas": True, "violaciones": [],
                                   "objetivos": {}, "riesgos": [], "resumen_ejecutivo": ""}, None)
    assert any("veredicto" in e for e in errores)


def test_propuesta_con_monto_fuera_de_rango():
    obj = {"campana": "Cultural", "diagnostico": "", "alternativas_evaluadas": [], "utilidad_esperada": 0.7,
           "propuesta": {"segment_id": 5, "presupuesto_restante_mxn": 900},
           "solicitud_al_broker": {"tipo": "exigir"}, "validacion": {}}
    errores = g.revisar_propuesta(obj, "Cultural", 500.0)
    assert any("900" in e for e in errores) and any("tipo" in e for e in errores)


# --------------------------------------------------------------------------- Human-in-the-Loop
ASIG = {"presupuesto_cultural_mxn": 250, "presupuesto_romantica_mxn": 250}


def test_aprobar_con_observaciones_exige_reconocerlas():
    aud = {"veredicto": "aprobado_con_observaciones"}
    with pytest.raises(g.DecisionInvalida):
        g.evaluar_decision_humana("aprobar", ASIG, aud)
    d = g.evaluar_decision_humana("aprobar", ASIG, aud, comentario="Revisado CPL", acepta_observaciones=True)
    assert d["cultural_mxn"] == 250 and d["validacion"]["valido"]


def test_veto_del_monitor_bloquea_aprobar_pero_permite_ajustar():
    aud = {"veredicto": "rechazado"}
    with pytest.raises(g.DecisionInvalida) as e:
        g.evaluar_decision_humana("aprobar", ASIG, aud, comentario="x", acepta_observaciones=True)
    assert e.value.veto
    d = g.evaluar_decision_humana("ajustar", ASIG, aud, cultural_mxn=225, romantica_mxn=275, comentario="Más ROI")
    assert d["accion"] == "ajustar" and d["romantica_mxn"] == 275


def test_ajuste_humano_se_revalida_en_servidor():
    with pytest.raises(g.DecisionInvalida) as e:
        g.evaluar_decision_humana("ajustar", ASIG, {"veredicto": "aprobado"},
                                  cultural_mxn=100, romantica_mxn=400, comentario="todo a Romántica")
    assert e.value.violaciones


def test_rechazar_exige_motivo():
    with pytest.raises(g.DecisionInvalida):
        g.evaluar_decision_humana("rechazar", ASIG, {"veredicto": "aprobado"})
    assert g.evaluar_decision_humana("rechazar", ASIG, {}, comentario="Esperar datos reales")["accion"] == "rechazar"
