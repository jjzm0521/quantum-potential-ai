"""
Designer agent: imagen/texto → Design JSON.

Estrategia:
  - Usa el system prompt detallado + few-shot examples
  - Fuerza chain of thought con etiquetas <analysis> <design> <self_critique>
  - Parsea las 3 secciones y devuelve un DesignerOutput estructurado

Modelo: Claude (la versión configurada en el sistema)
"""

from __future__ import annotations
import os
import base64
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from .prompts import designer_system, fewshot_for_dim


_CLIENT = None
_MODEL  = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _CLIENT


@dataclass
class DesignerOutput:
    design: dict                # el Design JSON listo para el composer
    analysis: str               # razonamiento del agente (sección <analysis>)
    self_critique: str          # auto-crítica (sección <self_critique>)
    confidence: str             # alta | media | baja
    confidence_breakdown: dict  # por componente
    raw_response: str           # respuesta completa por si falla el parsing


def design_from_text(description: str, force_dim: int = 0) -> DesignerOutput:
    """
    Genera un Design a partir de una descripción textual.
      force_dim=1 → fuerza 1D
      force_dim=2 → fuerza 2D
      force_dim=0 → la IA decide
    """
    messages = _build_fewshot_messages(force_dim)
    messages.append({"role": "user", "content": description})
    return _call_and_parse(messages, force_dim)


def design_from_image(
    image_bytes: bytes,
    mime_type: str = "image/png",
    extra_context: str = "",
    force_dim: int = 0,
) -> DesignerOutput:
    """Genera un Design a partir de una imagen (AFM/SEM/esquema)."""
    b64 = base64.standard_b64encode(image_bytes).decode()
    user_content = []
    if extra_context:
        user_content.append({"type": "text", "text": f"Contexto: {extra_context}"})
    user_content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type, "data": b64},
    })
    user_content.append({
        "type": "text",
        "text": ("Analiza esta imagen y devuelve la composición del potencial "
                 "siguiendo el formato establecido (<analysis>, <design>, "
                 "<self_critique>)."),
    })

    messages = _build_fewshot_messages(force_dim)
    messages.append({"role": "user", "content": user_content})
    return _call_and_parse(messages, force_dim)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _build_fewshot_messages(dim: int = 0) -> list[dict]:
    """Convierte fewshot al formato messages de Anthropic."""
    return [{"role": role, "content": content} for role, content in fewshot_for_dim(dim)]


def _call_and_parse(messages: list[dict], dim: int = 0) -> DesignerOutput:
    response = _client().messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=designer_system(dim=dim),
        messages=messages,
    )
    raw = response.content[0].text
    return _parse_output(raw)


def _parse_output(raw: str) -> DesignerOutput:
    """Extrae las 3 secciones del output del modelo."""
    analysis = _extract_section(raw, "analysis")
    design_str = _extract_section(raw, "design")
    critique = _extract_section(raw, "self_critique")

    # Parsear el JSON
    try:
        # quitar posibles bloques markdown ```json ... ```
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", design_str.strip())
        design = json.loads(cleaned)
    except Exception as e:
        raise ValueError(
            f"El JSON del Design no se pudo parsear:\n{design_str}\n\nError: {e}"
        )

    confidence, breakdown = _parse_confidence(critique)

    return DesignerOutput(
        design=design,
        analysis=analysis.strip(),
        self_critique=critique.strip(),
        confidence=confidence,
        confidence_breakdown=breakdown,
        raw_response=raw,
    )


def _extract_section(text: str, tag: str) -> str:
    """Extrae el contenido entre <tag>...</tag>."""
    pattern = rf"<{tag}>\s*(.*?)\s*</{tag}>"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        # Fallback: si no hay etiquetas pero solo hay un JSON, asumir que es <design>
        if tag == "design":
            jm = re.search(r"\{.*\}", text, re.DOTALL)
            if jm:
                return jm.group()
        return ""
    return m.group(1)


def _parse_confidence(critique: str) -> tuple[str, dict]:
    """Extrae 'Confianza global' y desglose por componente del bloque de self_critique."""
    global_match = re.search(
        r"confianza\s*global\s*:\s*(\w+)", critique, re.IGNORECASE
    )
    global_conf = (global_match.group(1).lower() if global_match else "media")

    breakdown = {}
    for line in critique.splitlines():
        m = re.search(r"-\s*([\w\s]+):\s*(alta|media|baja)", line, re.IGNORECASE)
        if m:
            key = m.group(1).strip().lower()
            val = m.group(2).lower()
            breakdown[key] = val

    return global_conf, breakdown
