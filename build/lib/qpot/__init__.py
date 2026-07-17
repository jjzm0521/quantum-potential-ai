"""
qpot — herramienta de línea de comandos para diseñar, ver, resolver y exportar
potenciales cuánticos SIN llamar a ninguna API.

Pensada para que un agente externo (Claude Code, ChatGPT, Codex, Antigravity) o un
humano manejen el mismo Design del proyecto activo en `workspace/`. El "cerebro" es el
LLM que ya tiene abierto el estudiante; este paquete es solo el conjunto de herramientas.

Uso típico:
    qpot project new demo --dim 1 --material GaAs
    python -m qpot new --dim 1 --material GaAs
    python -m qpot from-preset finite_well --dim 1 --params '{"depth":0.25,"L":30}'
    python -m qpot render
    python -m qpot solve --n-states 4
    python -m qpot verify
    python -m qpot export --format m
"""

__version__ = "1.0.0"

__all__ = ["session", "render", "cli", "projects", "verification"]
