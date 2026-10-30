"""Punto de entrada: corre el Crew completo sobre el caso de prueba y guarda el resultado.

Uso:  python main.py
Requiere .env con ANTHROPIC_API_KEY (ver .env.example).
"""
import json
from pathlib import Path

from crew import build_crew, entradas


def main():
    datos = entradas()
    print("Entradas del caso de prueba:\n" + json.dumps(datos, indent=2, ensure_ascii=False))
    resultado = build_crew().kickoff(inputs=datos)

    Path("logs").mkdir(exist_ok=True)
    Path("logs/resultado_final.md").write_text(str(resultado), encoding="utf-8")
    print("\n=== RESPUESTA FINAL ===\n" + str(resultado))


if __name__ == "__main__":
    main()
