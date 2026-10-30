"""Fija la semilla antes de importar nada, para que las pruebas no dependan de SIM_SEED en .env."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simulador  # noqa: E402

os.environ["SIM_SEED"] = str(simulador.DEFAULT_SEED)
