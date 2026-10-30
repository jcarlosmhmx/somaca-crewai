"""Configuración central: construye el LLM a partir de variables de entorno.

Cambiar de proveedor (Anthropic, OpenAI, Ollama) solo requiere editar .env.
"""
import os

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()



def get_llm() -> LLM:
    """Devuelve el LLM compartido por todos los agentes."""
    kwargs = {"model": os.getenv("MODEL", "anthropic/claude-haiku-5-5")}
    if os.getenv("TEMPERATURE"):  # los modelos Claude 5.x rechazan temperature
        kwargs["temperature"] = float(os.getenv("TEMPERATURE"))
    return LLM(**kwargs)
