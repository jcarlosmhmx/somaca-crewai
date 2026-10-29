"""Punto de entrada: corre el Crew completo y guarda el resultado.

Uso:  python main.py
"""
from crew import build_crew


def main():
    crew = build_crew()
    result = crew.kickoff()
    print(result)


if __name__ == "__main__":
    main()
