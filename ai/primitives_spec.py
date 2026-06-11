"""
Genera la documentación textual de las primitivas que se inyecta en los prompts.

Es la ÚNICA fuente de verdad: si cambias una primitiva en core/primitives.py,
aquí se actualiza automáticamente (lee del registry).
"""

from __future__ import annotations
from core.primitives import REGION_PRIMITIVES, PROFILE_PRIMITIVES
from core.primitives_dsl_1d import REGION_PRIMITIVES_1D, PROFILE_PRIMITIVES_1D


def primitives_documentation(dim: int = 2) -> str:
    """
    Devuelve doc de las primitivas para el system prompt.
    dim=1 → solo primitivas 1D. dim=2 → solo 2D. dim=0 → ambas.
    """
    lines = []

    if dim in (1, 0):
        lines.append("═══ PRIMITIVAS 1D (para problemas en una dimensión, V(x)) ═══\n")
        lines.append("REGIONES 1D (intervalos — usar dentro de 'mask' o 'where'):\n")
        for name, spec in REGION_PRIMITIVES_1D.items():
            lines.append(f"  • {name}({_format_args(spec)})")
            lines.append(f"      {spec.description}")
            for arg, help_ in spec.arg_help.items():
                if help_: lines.append(f"      - {arg}: {help_}")
            lines.append("")
        lines.append("\nPERFILES DE POTENCIAL 1D (V en eV — se SUMAN entre sí):\n")
        for name, spec in PROFILE_PRIMITIVES_1D.items():
            lines.append(f"  • {name}({_format_args(spec)})")
            lines.append(f"      {spec.description}")
            for arg, help_ in spec.arg_help.items():
                if help_: lines.append(f"      - {arg}: {help_}")
            lines.append("")

    if dim in (2, 0):
        lines.append("\n═══ PRIMITIVAS 2D (para problemas planares, V(x,y)) ═══\n")
        lines.append("REGIONES 2D (devuelven máscara booleana — dentro de 'mask' o 'where'):\n")
        for name, spec in REGION_PRIMITIVES.items():
            lines.append(f"  • {name}({_format_args(spec)})")
            lines.append(f"      {spec.description}")
            for arg, help_ in spec.arg_help.items():
                if help_: lines.append(f"      - {arg}: {help_}")
            lines.append("")
        lines.append("\nPERFILES DE POTENCIAL 2D (V en eV — se SUMAN entre sí):\n")
        for name, spec in PROFILE_PRIMITIVES.items():
            lines.append(f"  • {name}({_format_args(spec)})")
            lines.append(f"      {spec.description}")
            for arg, help_ in spec.arg_help.items():
                if help_: lines.append(f"      - {arg}: {help_}")
            lines.append("")

    lines.append("\nOPERACIONES COMPUESTAS (funcionan en 1D y 2D):\n")
    lines.append("  • mask(region, value): aplica 'value' (eV) dentro de la región, 0 fuera.")
    lines.append("  • where(region, inner, outer): 'inner' dentro, 'outer' fuera.")
    lines.append("  • clamp(inner, V_min, V_max): recorta al rango.")
    lines.append("  • scale(inner, factor): multiplica por escalar.")
    lines.append("  • union/intersection/complement: combina regiones.")

    return "\n".join(lines)


def _format_args(spec) -> str:
    items = []
    for k, v in spec.args.items():
        u = spec.arg_units.get(k, "")
        if u:
            items.append(f"{k}={v}[{u}]")
        else:
            items.append(f"{k}={v}")
    return ", ".join(items)


def design_schema() -> str:
    """Schema JSON estricto para el Design."""
    return """
DESIGN JSON SCHEMA:
{
  "dim": 2,                          // 1 o 2
  "material": "GaAs|InAs|InGaAs|Si|GaN|libre",
  "domain": {"L": <float nm>, "N": <int>},     // dominio cuadrado [-L/2, L/2]², grilla N×N
  "pieces": [
    {
      "label": "<descripción humana>",         // opcional
      "enabled": true,                          // opcional, default true
      "op": "<nombre_primitiva>",
      "args": {<argumentos>}
    },
    // ...para 'mask' o 'where':
    {
      "op": "mask",
      "region": { "op": "<región>", "args": {...} },
      "value": <float eV>
    },
    {
      "op": "where",
      "region": { "op": "<región>", "args": {...} },
      "inner": { "op": "...", "args": {...} },
      "outer": { "op": "constant", "args": {"value": 0} }
    }
  ]
}

REGLAS:
- Coordenadas en nm. Potencial en eV.
- Las pieces se SUMAN entre sí (orden no importa salvo por composiciones).
- Si no estás seguro de un parámetro, usa valores típicos del material.
- Usa raw_expr SOLO si ninguna primitiva sirve (último recurso).
"""
