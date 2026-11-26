"""Configuración central: construye el LLM a partir de variables de entorno.

Cambiar de proveedor (OpenAI, Anthropic, Ollama) solo requiere editar .env:
    MODEL=openai/gpt-5.4-mini            + OPENAI_API_KEY
    MODEL=anthropic/claude-haiku-5-5     + ANTHROPIC_API_KEY   (modelo de la corrida de la Fase 3)
    MODEL=ollama/llama3.1                + OLLAMA_BASE_URL=http://localhost:11434
"""
import os

from dotenv import load_dotenv

load_dotenv()

MODELO_POR_DEFECTO = "openai/gpt-5.4-mini"


def nombre_modelo() -> str:
    return os.getenv("MODEL", MODELO_POR_DEFECTO)


def llave_configurada() -> bool:
    """¿Hay credenciales para el proveedor elegido? (Ollama no las necesita.)"""
    proveedor = nombre_modelo().split("/", 1)[0].lower()
    requeridas = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    var = requeridas.get(proveedor)
    return True if var is None else bool(os.getenv(var))


def get_llm():
    """Devuelve el LLM compartido por todos los agentes."""
    from crewai import LLM  # import diferido: la API y las pruebas pueden cargar config sin CrewAI

    kwargs = {"model": nombre_modelo()}
    if os.getenv("TEMPERATURE"):  # algunos modelos (Claude 5.x, GPT-5.x) rechazan temperature
        kwargs["temperature"] = float(os.getenv("TEMPERATURE"))
    if os.getenv("OLLAMA_BASE_URL") and kwargs["model"].startswith("ollama/"):
        kwargs["base_url"] = os.getenv("OLLAMA_BASE_URL")
    return LLM(**kwargs)
