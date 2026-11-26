"""Rutas FastAPI de punta a punta con TestClient (modo respaldo, sin LLM)."""
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("SOMACA_DB", str(tmp_path / "api.db"))
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_salud_y_escenario(cliente):
    assert cliente.get("/salud").json()["ok"]
    esc = cliente.get("/escenario").json()
    assert esc["entradas"]["presupuesto_restante"] == pytest.approx(500, abs=0.1)
    assert cliente.get("/reparto/validar", params={"cultural": 300, "romantica": 300}).json()["valido"] is False


def test_flujo_completo_por_http(cliente):
    r = cliente.post("/ejecuciones", json={"modo": "replay", "velocidad": 20})
    assert r.status_code == 202
    eid = r.json()["id"]
    assert cliente.post("/ejecuciones", json={"modo": "replay"}).status_code == 409
    t0 = time.time()
    while cliente.get(f"/ejecuciones/{eid}").json()["estado"] != "completada":
        assert time.time() - t0 < 30
        time.sleep(0.1)
    with cliente.stream("GET", f"/ejecuciones/{eid}/eventos") as s:
        cuerpo = "".join(s.iter_text())
    assert "event: tarea_completada" in cuerpo and cuerpo.rstrip().endswith("data: {}")
    aud = cliente.get(f"/ejecuciones/{eid}/auditoria").json()
    assert aud["veredicto_monitor"] == "aprobado_con_observaciones"
    malo = cliente.post(f"/ejecuciones/{eid}/decision", json={"accion": "aprobar", "responsable": "Ingrid"})
    assert malo.status_code == 422
    ok = cliente.post(f"/ejecuciones/{eid}/decision", json={"accion": "aprobar", "responsable": "Ingrid",
                                                             "comentario": "Revisado", "acepta_observaciones": True})
    assert ok.status_code == 200 and ok.json()["accion"] == "aprobar"
    assert "APROBAR por Ingrid" in cliente.get(f"/ejecuciones/{eid}/reporte").text
    assert cliente.get("/ejecuciones/no-existe").status_code == 404
