"""Configuración central: construye el LLM a partir de variables de entorno.

Cambiar de proveedor (Anthropic, OpenAI, Ollama) solo requiere editar .env.
"""
import os

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

SEED = int(os.getenv("SIM_SEED", "42"))


def get_llm() -> LLM:
    """Devuelve el LLM compartido por todos los agentes."""
    return LLM(
        model=os.getenv("MODEL", "anthropic/claude-haiku-5-5"),
        temperature=float(os.getenv("TEMPERATURE", "0.2")),
    )
