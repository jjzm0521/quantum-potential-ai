"""
Agente IA que analiza una imagen AFM/SEM o una descripción de texto
y devuelve un potencial sugerido con parámetros iniciales.
"""

from __future__ import annotations
import os
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic

_CLIENT = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


@dataclass
class AnalysisResult:
    pot_name: str           # clave en POTENTIALS o POTENTIALS_1D
    params: dict            # parámetros sugeridos
    material: str           # clave en MATERIALS
    expr_str: str           # expresión COMSOL/MATLAB del potencial
    explanation: str        # explicación en español para el profe
    confidence: str         # "alta" / "media" / "baja"
    dim: int                # 1 o 2
    raw_json: dict


_SYSTEM_PROMPT = """\
Eres un experto en física de semiconductores y mecánica cuántica computacional.
Tu tarea es analizar una descripción textual o una imagen (AFM, SEM, STM, esquema)
de un potencial cuántico, decidir si es un problema 1D o 2D, e identificar qué tipo
de potencial corresponde.

Responde SIEMPRE con un JSON válido con esta estructura exacta:
{
  "dim": <1 o 2>,
  "pot_name": "<una clave de la lista correspondiente a dim>",
  "params": {<diccionario de parámetros con valores numéricos>},
  "material": "<GaAs | InAs | InGaAs | Si | GaN | libre>",
  "expr_str": "<expresión MATLAB del potencial; x en metros (y si dim=2 también y en metros)>",
  "explanation": "<2-3 oraciones en español: qué estructura, por qué ese potencial>",
  "confidence": "<alta | media | baja>"
}

CRITERIO PARA dim=1 vs dim=2:
- Si la descripción menciona "1D", "unidimensional", una sola coordenada,
  pozos/barreras simples sin geometría 2D explícita → dim=1
- Si menciona quantum dots circulares, anillos, geometría 2D, imagen AFM/SEM
  con estructura espacial extendida → dim=2
- Por defecto, una "barrera", "pozo", "doble pozo", "oscilador armónico" → dim=1
- "Quantum dot 2D", "imagen AFM de superficie" → dim=2

Potenciales 1D (dim=1):
- infinite_well:    L[nm]
- finite_well:      depth[eV], L[nm]
- harmonic:         omega_eV[eV/nm²], offset[nm]
- double_well:      depth[eV], separation[nm], sigma[nm]
- barrier:          height[eV], width[nm], offset[nm]
- step:             height[eV], offset[nm]
- poschl_teller:    depth[eV], alpha[nm⁻¹]
- morse:            De[eV], a[nm⁻¹], x0[nm]
- triangular:       force[eV/nm], x_wall[nm]
- gaussian_well:    depth[eV], sigma[nm], offset[nm]

Potenciales 2D (dim=2):
- quantum_dot:        depth[eV], sigma[nm], offset_x[nm], offset_y[nm]
- quantum_ring:       depth[eV], r0[nm], width[nm]
- double_dot:         depth[eV], sigma[nm], separation[nm]
- harmonic:           omega_eV[eV/nm²], offset_x[nm], offset_y[nm]
- rectangular_well:   depth[eV], Lx[nm], Ly[nm]
- saddle_point:       height[eV], curvx[eV/nm²], curvy[eV/nm²]
- triple_dot:         depth[eV], sigma[nm], r_triangle[nm]

Ejemplos expr_str:
- 1D quantum well:    "-0.3*(abs(x) < 15e-9)"
- 1D harmonic:        "0.5*0.0005*(x*1e9)^2"
- 2D quantum_dot:     "-0.3*exp(-(x^2+y^2)/(2*(20e-9)^2))"

Si es ambiguo, baja la confidence. No incluyas nada fuera del JSON."""


def analyze_text(description: str) -> AnalysisResult:
    """Analiza descripción textual del potencial."""
    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": description}],
    )
    return _parse_response(response.content[0].text)


def analyze_image(image_bytes: bytes, mime_type: str = "image/png",
                  extra_context: str = "") -> AnalysisResult:
    """Analiza imagen AFM/SEM codificada en bytes."""
    b64 = base64.standard_b64encode(image_bytes).decode()
    content = []
    if extra_context:
        content.append({"type": "text", "text": extra_context})
    content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type, "data": b64},
    })
    content.append({
        "type": "text",
        "text": "Analiza esta imagen y devuelve el JSON con el potencial cuántico correspondiente.",
    })

    response = _client().messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return _parse_response(response.content[0].text)


def _parse_response(text: str) -> AnalysisResult:
    # Extrae JSON aunque haya texto extra alrededor
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f"La IA no devolvió JSON válido:\n{text}")
    raw = json.loads(match.group())

    return AnalysisResult(
        pot_name=raw.get("pot_name", "quantum_dot"),
        params=raw.get("params", {}),
        material=raw.get("material", "GaAs"),
        expr_str=raw.get("expr_str", ""),
        explanation=raw.get("explanation", ""),
        confidence=raw.get("confidence", "media"),
        dim=int(raw.get("dim", 2)),
        raw_json=raw,
    )
