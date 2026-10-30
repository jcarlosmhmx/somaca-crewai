import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("crewai")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-falsa-solo-para-construir")


def test_entradas():
    from crew import entradas
    e = entradas()
    assert e["iteracion_corte"] == 24
    assert e["fecha_corte"] == "2026-11-14" and e["primer_dia_restante"] == "2026-11-15"
    assert e["ultimo_dia"] == "2026-11-20"
    assert e["presupuesto_restante"] == pytest.approx(500, abs=0.1)


def test_crew_se_construye_sin_llamar_al_llm():
    from crew import build_crew
    c = build_crew(log_file="/tmp/test_crew.log")
    assert len(c.agents) == 5 and len(c.tasks) == 5
    assert [a.allow_delegation for a in c.agents] == [False, False, False, True, False]
    assert all(a.tools for a in c.agents)
    t = c.tasks
    assert t[1].async_execution and t[2].async_execution
    assert not t[3].async_execution and not t[4].async_execution
    assert t[3].context == [t[1], t[2]]
    assert t[1].context == [t[0]]
