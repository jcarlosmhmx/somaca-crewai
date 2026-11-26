"""Capa de servicio de la API (sin servidor HTTP ni LLM): corrida de respaldo, SSE, auditoría y HITL."""
import time

import pytest


@pytest.fixture()
def servicio(tmp_path, monkeypatch):
    monkeypatch.setenv("SOMACA_DB", str(tmp_path / "prueba.db"))
    from api import servicio as s
    return s


def _esperar(s, eid, limite=30):
    t0 = time.time()
    while s.obtener(eid)["estado"] not in s.TERMINALES:
        assert time.time() - t0 < limite, "la corrida de respaldo no terminó"
        time.sleep(0.05)
    return s.obtener(eid)


@pytest.fixture()
def corrida(servicio):
    eid = servicio.iniciar("replay", velocidad=20)["id"]
    return servicio, eid, _esperar(servicio, eid)


def test_respaldo_completa_las_cinco_etapas(corrida):
    s, eid, ej = corrida
    assert ej["estado"] == "completada"
    assert [e["estado"] for e in ej["etapas"]] == ["completada"] * 5
    assert all(e["guardrail"] == "aprobado" for e in ej["etapas"])
    broker = ej["etapas"][3]
    assert broker["delegaciones"] == 2  # el Broker pidió aclaraciones a ambas campañas


def test_solo_una_ejecucion_a_la_vez(servicio):
    eid = servicio.iniciar("replay", velocidad=20)["id"]
    with pytest.raises(servicio.Ocupado):
        servicio.iniciar("replay")
    _esperar(servicio, eid)


def test_sse_entrega_todos_los_eventos_y_cierra(corrida):
    s, eid, _ = corrida
    mensajes = list(s.flujo_sse(eid, intervalo=0.01))
    assert mensajes[-1].startswith("event: fin")
    assert sum(m.startswith("id: ") for m in mensajes) == len(s.eventos_desde(eid))
    # reconexión: desde el evento 10 solo llegan los posteriores
    assert sum(m.startswith("id: ") for m in s.flujo_sse(eid, desde=10, intervalo=0.01)) == len(s.eventos_desde(eid)) - 10


def test_auditoria_revalida_y_evalua_peas(corrida):
    s, eid, _ = corrida
    a = s.auditoria(eid)
    assert a["veredicto_monitor"] == "aprobado_con_observaciones"
    assert a["validacion_reparto"]["valido"]
    assert all(g["ok"] for g in a["guardrails"])
    cumple = {m["metrica"]: m["cumple"] for m in a["evaluacion_peas"]["metricas"]}
    assert cumple["CTR acumulado"] and cumple["ROAS global"] and not cumple["Leads (12 días)"]
    assert a["evaluacion_peas"]["mejora_vs_base"]["leads"] > 0  # el cambio a segmento 5 suma leads
    assert {al["nivel"] for al in a["alertas"]} >= {"observacion", "info"}


def test_decision_humana_y_reporte(corrida):
    s, eid, _ = corrida
    import guardrails as g
    with pytest.raises(g.DecisionInvalida):
        s.registrar_decision(eid, "aprobar", responsable="Arantza")  # faltan reconocimiento y comentario
    with pytest.raises(g.DecisionInvalida):
        s.registrar_decision(eid, "ajustar", 0, 500, "todo a Romántica", "Arantza")
    d = s.registrar_decision(eid, "ajustar", 230, 270, "Más ROI en Romántica", "Arantza")
    assert (d["cultural_mxn"], d["romantica_mxn"], d["responsable"]) == (230, 270, "Arantza")
    with pytest.raises(s.Conflicto):
        s.registrar_decision(eid, "rechazar", comentario="otra", responsable="Víctor")
    md = s.reporte_markdown(eid)
    assert "AJUSTAR por Arantza" in md and "Evaluación determinista" in md


def test_crewai_sin_llave_se_rechaza_con_mensaje_claro(servicio, monkeypatch):
    monkeypatch.setenv("MODEL", "openai/gpt-5.4-mini")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="llave"):
        servicio.iniciar("crewai")


def test_formato_de_eventos():
    from ui.formato import evento_md
    assert "delega" in evento_md({"tipo": "paso", "agente": "Broker de Presupuesto", "clase": "AgentAction",
                                  "delegacion": True, "entrada": "¿mantienes 300?"})
    assert "rechazó" in evento_md({"tipo": "guardrail", "agente": "Broker de Presupuesto", "ok": False,
                                   "guardrail": "reparto", "errores": ["no conserva el total"]})
    linea = evento_md({"tipo": "herramienta", "herramienta": "validar_restricciones", "ok": False,
                       "salida": '{"valido": false, "violaciones": ["Cambio +2000% excede ±20%"]}'})
    assert "INVÁLIDO" in linea


def test_salidas_largas_se_guardan_completas(servicio):
    """Regresión: la salida de una tarea (>4,000 caracteres) no debe recortarse al guardarse."""
    import json
    import eventos
    eid = "prueba-larga"
    with servicio.conexion() as con:
        con.execute("INSERT INTO ejecuciones VALUES (?,?,?,?,?,?,?,?,?)",
                    (eid, 0, None, "en_ejecucion", "crewai", "x", json.dumps({}), None, None))
    salida = json.dumps({"veredicto": "aprobado", "resumen_ejecutivo": "x" * 6000})
    grab = servicio.Grabadora(eid)
    eventos.suscribir(grab)
    try:
        eventos.emitir("tarea_completada", tarea="T5 Auditoría", agente="Monitor Global de Cumplimiento",
                       salida=salida)
    finally:
        eventos.desuscribir(grab)
    s = servicio.salidas(eid)["auditoria"]
    assert s["error_json"] is None and s["json"]["veredicto"] == "aprobado"
