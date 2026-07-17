"""
Utilidades de soporte SIN llamadas a API.

El antiguo pipeline multi-agente (designer/verifier/refiner/vision/pipeline) que llamaba a
la API de Anthropic se archivó en `legacy/`. El flujo nuevo lo ejecuta el agente externo
(Claude Code / ChatGPT / Codex / Antigravity) usando el CLI `qpot`.

Aquí quedan solo módulos sin dependencia de `anthropic`:
  - validators        validación numérica/estructural del Design
  - primitives_spec   documentación de primitivas y esquema (fuente única)
  - event_log         registro de eventos en disco
  - agent_harness     helpers de sesión / contrato del diseño
"""

from .validators import validate_design

__all__ = ["validate_design"]
