"""
Validadores numéricos del Design — SIN IA.

Estos chequeos corren ANTES de mandar el Design al verifier multimodal
para atrapar errores triviales rápido (no quemar tokens de IA).

Cada validador devuelve una lista de issues (strings). Vacía = OK.
"""

from __future__ import annotations
import numpy as np
from typing import Iterable
from core.primitives import ALL_PRIMITIVES, REGION_PRIMITIVES, PROFILE_PRIMITIVES
from core.primitives_dsl_1d import REGION_PRIMITIVES_1D, PROFILE_PRIMITIVES_1D
from core.composer import evaluate_design, evaluate_design_1d
from core.harnex import validate_harnex_header


# ---------------------------------------------------------------------------
# Validador maestro
# ---------------------------------------------------------------------------

def validate_design(design: dict, X=None, Y=None, x_1d=None) -> list[str]:
    """
    Corre todos los validadores. Retorna lista de issues encontrados.
    Para 2D pasar X, Y (mesh arrays). Para 1D pasar x_1d (array 1D).
    """
    issues = []
    issues += validate_schema(design)
    issues += validate_harnex_header(design)
    issues += validate_pieces_structure(design)
    issues += validate_physics_scales(design)
    if design.get("dim") == 1 and x_1d is not None:
        issues += validate_numerical_1d(design, x_1d)
    elif X is not None and Y is not None:
        issues += validate_numerical(design, X, Y)
    return issues


def validate_numerical_1d(design: dict, x: np.ndarray) -> list[str]:
    """Evalúa Design 1D y chequea: no NaN, rangos razonables."""
    issues = []
    try:
        V = evaluate_design_1d(design, x)
    except Exception as e:
        return [f"Error evaluando Design 1D: {e}"]
    if not np.all(np.isfinite(V)):
        issues.append(f"V tiene {np.sum(~np.isfinite(V))} NaN/Inf.")
    # Excluir paredes infinitas para el chequeo de rango
    V_finite = V[np.abs(V) < 100]
    if len(V_finite) > 0:
        V_range = float(V_finite.max() - V_finite.min())
        if V_range > 50.0:
            issues.append(f"Rango de V (excluyendo paredes) = {V_range:.2f} eV >50 eV.")
        if V_range < 1e-6:
            issues.append("V casi constante — sin estructura.")
    return issues


# ---------------------------------------------------------------------------
# Schema y estructura
# ---------------------------------------------------------------------------

def validate_schema(design: dict) -> list[str]:
    issues = []
    if not isinstance(design, dict):
        return ["Design no es un dict."]

    if "dim" not in design:
        issues.append("Falta campo 'dim'.")
    elif design["dim"] not in (1, 2):
        issues.append(f"'dim' debe ser 1 o 2, no {design['dim']}.")

    if "pieces" not in design:
        issues.append("Falta campo 'pieces'.")
    elif not isinstance(design["pieces"], list):
        issues.append("'pieces' debe ser una lista.")
    elif len(design["pieces"]) == 0:
        issues.append("'pieces' está vacía — no hay potencial.")

    if "material" in design:
        valid_mats = {"GaAs", "InAs", "InGaAs", "Si", "GaN", "libre"}
        if design["material"] not in valid_mats:
            issues.append(f"Material '{design['material']}' no reconocido. "
                          f"Válidos: {valid_mats}")

    if "domain" in design:
        dom = design["domain"]
        if not isinstance(dom, dict):
            issues.append("'domain' debe ser dict {L, N}.")
        else:
            if "L" in dom and (dom["L"] <= 0 or dom["L"] > 5000):
                issues.append(f"Dominio L={dom['L']} fuera de [0, 5000] nm.")
            if "N" in dom and (dom["N"] < 16 or dom["N"] > 2048):
                issues.append(f"Resolución N={dom['N']} fuera de [16, 2048].")

    return issues


def validate_pieces_structure(design: dict) -> list[str]:
    issues = []
    dim = design.get("dim", 2)
    profiles_avail = PROFILE_PRIMITIVES_1D if dim == 1 else PROFILE_PRIMITIVES
    regions_avail  = REGION_PRIMITIVES_1D  if dim == 1 else REGION_PRIMITIVES
    for i, piece in enumerate(design.get("pieces", [])):
        if not isinstance(piece, dict):
            issues.append(f"Pieza #{i} no es dict.")
            continue
        if "op" not in piece:
            issues.append(f"Pieza #{i} sin 'op'.")
            continue
        op = piece["op"]
        composed = {"mask", "where", "clamp", "scale", "sum"}
        if op in composed:
            issues += _validate_composed(piece, i)
        elif op in profiles_avail:
            issues += _validate_primitive_args(piece, i, profiles_avail[op])
        elif op in regions_avail:
            issues.append(f"Pieza #{i}: '{op}' es una región. Debe ir dentro de mask/where.")
        else:
            issues.append(f"Pieza #{i}: operación desconocida '{op}' para dim={dim}.")
    return issues


def _validate_composed(piece: dict, i: int) -> list[str]:
    issues = []
    op = piece["op"]
    if op == "mask":
        if "region" not in piece: issues.append(f"Pieza #{i} (mask) sin 'region'.")
        if "value" not in piece: issues.append(f"Pieza #{i} (mask) sin 'value'.")
    elif op == "where":
        if "region" not in piece: issues.append(f"Pieza #{i} (where) sin 'region'.")
        if "inner" not in piece:  issues.append(f"Pieza #{i} (where) sin 'inner'.")
        if "outer" not in piece:  issues.append(f"Pieza #{i} (where) sin 'outer'.")
    elif op == "clamp":
        if "inner" not in piece: issues.append(f"Pieza #{i} (clamp) sin 'inner'.")
    elif op == "scale":
        if "inner" not in piece:  issues.append(f"Pieza #{i} (scale) sin 'inner'.")
        if "factor" not in piece: issues.append(f"Pieza #{i} (scale) sin 'factor'.")
    return issues


def _validate_primitive_args(piece: dict, i: int, spec) -> list[str]:
    issues = []
    args = piece.get("args", {})
    for required in spec.args:
        # No es obligatorio que estén todos — los faltantes usan default.
        # Solo chequear tipos si están.
        if required in args:
            val = args[required]
            if isinstance(spec.args[required], (int, float)) and not isinstance(val, (int, float)):
                issues.append(f"Pieza #{i} arg '{required}' debe ser numérico, recibido {type(val).__name__}.")
            if isinstance(spec.args[required], list) and not isinstance(val, (list, tuple)):
                issues.append(f"Pieza #{i} arg '{required}' debe ser lista, recibido {type(val).__name__}.")
    return issues


# ---------------------------------------------------------------------------
# Sanity físico
# ---------------------------------------------------------------------------

_DEPTH_MAX_EV = 2.0    # nadie pone pozos cuánticos de >2 eV
_DEPTH_MIN_MEV = 1.0   # menos de 1 meV es ruido
_SIGMA_MIN_NM = 0.5
_SIGMA_MAX_NM = 500.0


def validate_physics_scales(design: dict) -> list[str]:
    """Chequea que los parámetros estén en rangos físicamente razonables."""
    issues = []
    for i, piece in enumerate(design.get("pieces", [])):
        op = piece.get("op")
        args = piece.get("args", {})

        if op in ("gaussian", "exp_decay"):
            amp = abs(args.get("amplitude", 0))
            if amp > _DEPTH_MAX_EV:
                issues.append(f"Pieza #{i} ({op}): amplitude={amp} eV demasiado grande (>2 eV).")
            sig = args.get("sigma", args.get("length", 10))
            if not (_SIGMA_MIN_NM <= sig <= _SIGMA_MAX_NM):
                issues.append(f"Pieza #{i} ({op}): sigma/length={sig} fuera de [{_SIGMA_MIN_NM}, {_SIGMA_MAX_NM}] nm.")

        if op == "mexican_hat":
            depth = args.get("depth", 0)
            if depth <= 0 or depth > _DEPTH_MAX_EV:
                issues.append(f"Pieza #{i}: depth={depth} debe estar en (0, 2] eV.")
            r0 = args.get("r0", 0)
            if r0 <= 0 or r0 > 200:
                issues.append(f"Pieza #{i}: r0={r0} nm fuera de (0, 200].")

        if op == "coulomb":
            eps = args.get("eps_r", 1)
            if eps < 1 or eps > 50:
                issues.append(f"Pieza #{i} (coulomb): eps_r={eps} fuera de [1, 50].")
            reg = args.get("regularization", 1)
            if reg <= 0 or reg > 20:
                issues.append(f"Pieza #{i} (coulomb): regularization={reg} fuera de (0, 20] nm.")

        if op == "harmonic_2d":
            w = args.get("omega_eV", 0)
            if w <= 0 or w > 0.1:
                issues.append(f"Pieza #{i} (harmonic_2d): omega_eV={w} fuera de (0, 0.1] eV/nm².")

    return issues


# ---------------------------------------------------------------------------
# Evaluación numérica
# ---------------------------------------------------------------------------

def validate_numerical(design: dict, X: np.ndarray, Y: np.ndarray) -> list[str]:
    """Evalúa el Design y chequea: no NaN, rangos razonables, no domina la grilla."""
    issues = []
    try:
        V = evaluate_design(design, X, Y)
    except Exception as e:
        return [f"Error evaluando Design: {e}"]

    if not np.all(np.isfinite(V)):
        issues.append(f"V contiene {np.sum(~np.isfinite(V))} valores NaN/Inf.")

    V_range = float(V.max() - V.min())
    if V_range > 100.0:   # 100 eV de rango es absurdo
        issues.append(f"Rango de V={V_range:.2f} eV demasiado grande (>100 eV). "
                      f"Probable bug en algún coeficiente.")
    if V_range < 1e-6:
        issues.append("V es prácticamente constante — sin estructura para resolver.")

    return issues
