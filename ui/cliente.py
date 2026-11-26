"""Cliente HTTP de la API de SOMACA (REST + Server-Sent Events), usado por la GUI de Streamlit.

No depende de Streamlit, así que se puede probar o usar desde un notebook.
"""
from __future__ import annotations

import json
from typing import Iterator

import requests


class ApiError(RuntimeError):
    def __init__(self, status: int, detalle):
        self.status = status
        self.detalle = detalle
        texto = detalle.get("motivo") if isinstance(detalle, dict) else detalle
        super().__init__(f"HTTP {status}: {texto}")


class Cliente:
    def __init__(self, base: str = "http://localhost:8000", timeout: float = 15):
        self.base = base.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ REST
    def _req(self, metodo: str, ruta: str, **kw):
        try:
            r = requests.request(metodo, self.base + ruta, timeout=kw.pop("timeout", self.timeout), **kw)
        except requests.RequestException as e:
            raise ApiError(0, f"No se pudo conectar con la API en {self.base} ({type(e).__name__}).") from None
        if r.status_code >= 400:
            try:
                detalle = r.json().get("detail", r.text)
            except ValueError:
                detalle = r.text
            raise ApiError(r.status_code, detalle)
        ctype = r.headers.get("content-type", "")
        return r.json() if "json" in ctype else r.text

    def salud(self):
        return self._req("GET", "/salud", timeout=3)

    def escenario(self):
        return self._req("GET", "/escenario")

    def serie(self):
        return self._req("GET", "/escenario/serie")

    def linea_base(self):
        return self._req("GET", "/escenario/linea-base")

    def validar_reparto(self, cultural: float, romantica: float):
        return self._req("GET", "/reparto/validar", params={"cultural": cultural, "romantica": romantica})

    def iniciar(self, modo: str = "crewai", velocidad: float | None = None):
        body = {"modo": modo}
        if velocidad:
            body["velocidad"] = velocidad
        return self._req("POST", "/ejecuciones", json=body)

    def listar(self):
        return self._req("GET", "/ejecuciones")

    def obtener(self, eid: str):
        return self._req("GET", f"/ejecuciones/{eid}")

    def eventos_json(self, eid: str, desde: int = 0):
        return self._req("GET", f"/ejecuciones/{eid}/eventos.json", params={"desde": desde})

    def auditoria(self, eid: str):
        return self._req("GET", f"/ejecuciones/{eid}/auditoria")

    def decidir(self, eid: str, **datos):
        return self._req("POST", f"/ejecuciones/{eid}/decision", json=datos)

    def reporte(self, eid: str) -> str:
        return self._req("GET", f"/ejecuciones/{eid}/reporte")

    # ------------------------------------------------------------------ SSE
    def eventos(self, eid: str, desde: int = 0, timeout_lectura: float = 60) -> Iterator[dict]:
        """Itera los eventos SSE de una ejecución hasta el evento 'fin'."""
        try:
            r = requests.get(f"{self.base}/ejecuciones/{eid}/eventos", params={"desde": desde}, stream=True,
                             headers={"Accept": "text/event-stream"}, timeout=(5, timeout_lectura))
        except requests.RequestException as e:
            raise ApiError(0, f"No se pudo abrir el flujo de eventos ({type(e).__name__}).") from None
        if r.status_code >= 400:
            raise ApiError(r.status_code, r.text)
        tipo, datos = None, []
        with r:
            for linea in r.iter_lines(decode_unicode=True):
                if linea is None:
                    continue
                if linea == "":  # fin de un mensaje SSE
                    if tipo == "fin":
                        return
                    if datos:
                        try:
                            yield json.loads("\n".join(datos))
                        except ValueError:
                            pass
                    tipo, datos = None, []
                elif linea.startswith(":"):
                    continue  # latido
                elif linea.startswith("event:"):
                    tipo = linea[6:].strip()
                elif linea.startswith("data:"):
                    datos.append(linea[5:].lstrip())
