"""Punto de entrada: corre el Crew completo sobre el caso de prueba y guarda el resultado.

Uso:  python main.py
Requiere .env con la llave del proveedor elegido en MODEL (ver .env.example).
Para la GUI con monitor en vivo y Human-in-the-Loop usa la API + Streamlit (ver README).
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

    # Consumo de tokens de la corrida (para estimar el costo en la consola del proveedor)
    uso = getattr(resultado, "token_usage", None)
    if uso is not None:
        Path("logs/uso_tokens.txt").write_text(str(uso), encoding="utf-8")
        print("\n=== USO DE TOKENS ===\n" + str(uso))


if __name__ == "__main__":
    main()
