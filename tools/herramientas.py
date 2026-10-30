"""Envoltorios @tool de CrewAI sobre tools/logica.py.

Cada herramienta devuelve un JSON (str). Si la entrada es inválida devuelve
{"error": "..."} para que el agente pueda corregir su llamada.
"""
import json

from crewai.tools import tool

from tools import logica


def _json(fn, *args, **kwargs) -> str:
    try:
        return json.dumps(fn(*args, **kwargs), ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool("consultar_cpm_mercado")
def consultar_cpm_mercado(fecha: str) -> str:
    """Devuelve el período de mercado (día laboral, fin de semana, temporada alta o evento
    especial) y el rango de CPM en MXN para una fecha. Parámetro: fecha en formato AAAA-MM-DD."""
    return _json(logica.consultar_cpm, fecha)


@tool("leer_inventario_audiencias")
def leer_inventario_audiencias(campana: str) -> str:
    """Lista los segmentos de audiencia de una campaña ('Cultural' o 'Romantica') con su
    tasa de conversión, rango de CPM y CTR esperado. Úsala antes de proponer un cambio de audiencia."""
    return _json(logica.inventario, campana)


@tool("leer_metricas_campana")
def leer_metricas_campana(campana: str, hasta_iteracion: int = 24) -> str:
    """Lee el desempeño acumulado de una campaña ('Cultural' o 'Romantica') hasta una iteración
    de 6 horas (por defecto la 24, es decir, los primeros 6 días de 12): gasto, impresiones, clics,
    CTR, leads, CPL, ROAS, ROI, estabilidad, segmento actual y presupuesto disponible."""
    return _json(logica.metricas, campana, hasta_iteracion)


@tool("calcular_utilidad")
def calcular_utilidad(campana: str, conversiones: float, roi: float, estabilidad: float) -> str:
    """Calcula U = conversiones*w1 + ROI*w2 + estabilidad*w3 con los pesos de la campaña, cada
    término normalizado a [0,1]. 'conversiones' son los leads totales proyectados a 12 días;
    'roi' es (ingresos-gasto)/gasto; 'estabilidad' va de 0 a 1."""
    return _json(logica.utilidad, campana, conversiones, roi, estabilidad)


@tool("proyectar_escenario")
def proyectar_escenario(campana: str, segment_id: int, presupuesto_mxn: float) -> str:
    """Proyecta leads, CPL, ROAS, ROI y utilidad a 12 días si, desde la iteración 25, la campaña
    gasta 'presupuesto_mxn' MXN en el segmento 'segment_id'. Sirve para comparar alternativas
    (otro segmento u otro presupuesto) antes de decidir."""
    return _json(logica.proyectar_escenario, campana, segment_id, presupuesto_mxn)


@tool("validar_restricciones")
def validar_restricciones(campana: str, cambio_presupuesto_pct: float = 0.0, cambio_puja_pct: float = 0.0,
                          cambios_audiencia: int = 0, pausar: bool = False, roi_actual: float = None) -> str:
    """Valida una acción de campaña contra las reglas del PEAS: presupuesto máx ±20% por iteración
    (0.2 = 20%), puja/CPM máx ±10%, máx 1 cambio de audiencia, y pausar solo si el ROI es < 0.5x.
    Devuelve valido, violaciones y advertencias."""
    return _json(logica.validar_accion, campana, cambio_presupuesto_pct, cambio_puja_pct,
                 cambios_audiencia, pausar, roi_actual)


@tool("validar_reparto_presupuesto")
def validar_reparto_presupuesto(nuevo_cultural: float, nuevo_romantica: float) -> str:
    """Valida un nuevo reparto del presupuesto RESTANTE (en MXN) entre las campañas: debe
    conservar el total y ningún presupuesto puede cambiar más de ±20%."""
    return _json(logica.validar_reparto, nuevo_cultural, nuevo_romantica)


TODAS = [consultar_cpm_mercado, leer_inventario_audiencias, leer_metricas_campana, calcular_utilidad,
         proyectar_escenario, validar_restricciones, validar_reparto_presupuesto]
