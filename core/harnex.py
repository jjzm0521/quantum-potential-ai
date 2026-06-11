"""
Harnex header — metadata versionada del Design + validador pre-export a COMSOL.

El header `harnex` es un bloque opcional en la raíz del Design que documenta:
- versión del esquema
- identidad y propósito del pozo
- justificación de material y dominio
- observables esperados (lo que se va a medir en COMSOL)
- contacto / owner

Inspirado en la sección "Metadatos" de la plantilla Harnex propuesta en el
informe de deep-research. La idea es que el Design siga siendo la fuente de
verdad, pero que cargue consigo su propia ficha auditable.

El validador `validate_for_comsol_export` corre antes de `export_mph` y bloquea
exports que el modelo COMSOL no podría construir o que producirían resultados
sin sentido.
"""

from __future__ import annotations

from typing import Any

HARNEX_SCHEMA_VERSION = "0.1"

# Materiales que el exporter MPh sabe mapear a parámetros físicos.
_COMSOL_KNOWN_MATERIALS = {"GaAs", "InAs", "InGaAs", "Si", "GaN", "libre"}

_DOMAIN_L_MIN_NM = 1.0
_DOMAIN_L_MAX_NM = 5000.0
_DOMAIN_N_MIN = 16
_DOMAIN_N_MAX = 2048

_M_EFF_MIN = 1e-3
_M_EFF_MAX = 10.0

_N_STATES_MIN = 1
_N_STATES_MAX = 50


def default_harnex_header(
    *,
    well_id: str,
    purpose: str,
    material: str,
    domain_L_nm: float,
    domain_N: int,
    expected_observables: list[str] | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Construye un header harnex con los campos mínimos recomendados."""
    return {
        "schema_version": HARNEX_SCHEMA_VERSION,
        "id": well_id,
        "purpose": purpose,
        "material_justification": f"Se usa {material} por defecto.",
        "domain_rationale": (
            f"L={domain_L_nm} nm con N={domain_N} puntos; "
            f"resolución dx≈{domain_L_nm/domain_N:.3f} nm."
        ),
        "expected_observables": expected_observables or ["eigenvalores", "funciones de onda"],
        "owner": owner,
    }


def validate_harnex_header(design: dict) -> list[str]:
    """
    Valida el bloque `harnex` si está presente. Si no está, no es error
    (el header es opcional para mantener compat).
    """
    if "harnex" not in design:
        return []
    h = design["harnex"]
    if not isinstance(h, dict):
        return ["'harnex' debe ser un dict."]
    issues: list[str] = []
    ver = h.get("schema_version")
    if not isinstance(ver, str):
        issues.append("'harnex.schema_version' debe ser str.")
    elif ver != HARNEX_SCHEMA_VERSION:
        issues.append(
            f"'harnex.schema_version'={ver} no coincide con esperado "
            f"{HARNEX_SCHEMA_VERSION}."
        )
    for key in ("id", "purpose"):
        if key not in h or not isinstance(h[key], str) or not h[key].strip():
            issues.append(f"'harnex.{key}' debe ser str no vacío.")
    obs = h.get("expected_observables")
    if obs is not None and not (isinstance(obs, list) and all(isinstance(o, str) for o in obs)):
        issues.append("'harnex.expected_observables' debe ser lista de str.")
    return issues


def validate_for_comsol_export(
    design: dict,
    material_name: str,
    m_eff: float,
    n_states: int,
) -> list[str]:
    """
    Chequeos duros antes de llamar a `export_mph`. Devuelve lista de issues;
    vacía = OK para exportar. El exporter debe usar esto como puerta.
    """
    issues: list[str] = []

    # dim debe ser 1 o 2
    dim = design.get("dim")
    if dim not in (1, 2):
        issues.append(f"Export a COMSOL requiere dim=1 o 2, recibido dim={dim}.")

    # pieces no vacío
    pieces = design.get("pieces", [])
    if not isinstance(pieces, list) or len(pieces) == 0:
        issues.append("Design sin 'pieces' — no hay potencial para exportar.")

    # domain L/N obligatorios y en rango
    dom = design.get("domain")
    if not isinstance(dom, dict):
        issues.append("Falta 'domain' o no es dict — COMSOL necesita L y N.")
    else:
        L = dom.get("L")
        N = dom.get("N")
        if not isinstance(L, (int, float)) or not (_DOMAIN_L_MIN_NM <= L <= _DOMAIN_L_MAX_NM):
            issues.append(
                f"domain.L={L} fuera de [{_DOMAIN_L_MIN_NM}, {_DOMAIN_L_MAX_NM}] nm."
            )
        if not isinstance(N, int) or not (_DOMAIN_N_MIN <= N <= _DOMAIN_N_MAX):
            issues.append(
                f"domain.N={N} fuera de [{_DOMAIN_N_MIN}, {_DOMAIN_N_MAX}]."
            )

    # material conocido por el exporter
    if material_name not in _COMSOL_KNOWN_MATERIALS:
        issues.append(
            f"material='{material_name}' no está en el set conocido "
            f"{sorted(_COMSOL_KNOWN_MATERIALS)}."
        )

    # masa efectiva razonable
    if not isinstance(m_eff, (int, float)) or not (_M_EFF_MIN <= m_eff <= _M_EFF_MAX):
        issues.append(f"m_eff={m_eff} fuera de [{_M_EFF_MIN}, {_M_EFF_MAX}] m_e.")

    # n_states razonable
    if not isinstance(n_states, int) or not (_N_STATES_MIN <= n_states <= _N_STATES_MAX):
        issues.append(
            f"n_states={n_states} fuera de [{_N_STATES_MIN}, {_N_STATES_MAX}]."
        )

    # Si hay header harnex, validarlo también
    issues += validate_harnex_header(design)

    # El composer debe poder construir la expresión MATLAB
    try:
        if dim == 1:
            from .composer import design_to_matlab_expr_1d
            expr_str = design_to_matlab_expr_1d(design)
        else:
            from .composer import design_to_matlab_expr
            expr_str = design_to_matlab_expr(design)
        if not isinstance(expr_str, str) or not expr_str.strip():
            issues.append("design_to_matlab_expr produjo expresión vacía.")
    except Exception as e:
        issues.append(f"No se pudo construir expresión MATLAB para COMSOL: {e}")

    return issues


class ComsolExportError(ValueError):
    """Pre-export validation falló — el .mph no se generó."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("Pre-export a COMSOL bloqueado:\n  - " + "\n  - ".join(issues))
