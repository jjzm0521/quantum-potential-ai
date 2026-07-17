"""
Composer: evalúa un Design (lista de "pieces") sobre una grilla 2D
y devuelve V(x,y) en eV.

Un Design es un dict con esta estructura:

{
  "dim": 2,
  "material": "GaAs",
  "domain": {"L": 200.0, "N": 128},
  "pieces": [
    {
      "label": "anillo principal",       # opcional, para UI
      "enabled": true,                   # opcional, default true
      "op": "mexican_hat",               # nombre de la primitiva
      "args": {"center":[0,0], "r0":40, "depth":0.3}
    },
    {
      "label": "barrera lateral",
      "op": "mask",
      "region": {"op": "disk", "args": {"center":[15,0], "radius":5}},
      "value": 0.1                       # constante eV dentro del disco
    },
    {
      "op": "where",
      "region": {"op": "rectangle", "args": {"Lx":100,"Ly":100}},
      "inner": {"op": "gaussian", "args": {"center":[0,0], "amplitude":-0.3, "sigma":15}},
      "outer": {"op": "constant", "args": {"value": 0.5}}
    }
  ]
}

Cada pieza es aditiva por defecto (se suman).
"""

from __future__ import annotations
import copy
import re
import numpy as np
from qpot.schema import parameter_values
from .primitives import (
    ALL_PRIMITIVES, REGION_PRIMITIVES, PROFILE_PRIMITIVES,
    op_mask, op_where, op_clamp,
)
from .primitives_dsl_1d import (
    REGION_PRIMITIVES_1D, PROFILE_PRIMITIVES_1D,
)


# ---------------------------------------------------------------------------
# Parámetros nombrados: "definir geometría a partir de parámetros"
# ---------------------------------------------------------------------------

# Claves cuyo valor es estructural (no una referencia a parámetro) y no se sustituyen.
_PARAM_RESERVED_KEYS = {"op", "label", "axis", "side", "material", "kind", "enabled"}


def resolve_params(design: dict) -> dict:
    """Devuelve una copia del Design con las referencias a `parameters` sustituidas
    por sus valores numéricos.

    El Design puede traer un bloque raíz `"parameters": {"R1":12,"R2":28,"n":7,"Vb":0.228}`
    y las args/value de las piezas pueden ser un número o el NOMBRE de un parámetro
    (string que coincide con una clave de `parameters`), p. ej. `"R":"R2"`, `"value":"Vb"`.
    Para evaluar/resolver se sustituyen; para exportar a COMSOL se conservan los nombres.
    """
    params = parameter_values(design)
    if not params:
        return design

    def expr_with_params(expr: str) -> str:
        out = expr
        for name, value in params.items():
            if isinstance(value, (int, float)):
                out = re.sub(rf"\b{re.escape(name)}\b", repr(value), out)
        return out

    def sub(val):
        if isinstance(val, str):
            return params.get(val, val)
        if isinstance(val, list):
            return [sub(v) for v in val]
        if isinstance(val, dict):
            if val.get("op") == "raw_expr" and isinstance(val.get("args", {}).get("expr"), str):
                copied = copy.deepcopy(val)
                copied["args"]["expr"] = expr_with_params(copied["args"]["expr"])
                return copied
            return {k: (v if k in _PARAM_RESERVED_KEYS else sub(v)) for k, v in val.items()}
        return val

    d = copy.deepcopy(design)
    d["pieces"] = sub(d.get("pieces", []))
    return d


# ---------------------------------------------------------------------------
# Evaluación 2D
# ---------------------------------------------------------------------------

def evaluate_design(design: dict, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """
    Evalúa un Design 2D sobre la grilla (X, Y) y devuelve V en eV.
    Suma todas las pieces habilitadas.
    """
    V = np.zeros(X.shape, dtype=float)
    for i, piece in enumerate(design.get("pieces", [])):
        if piece.get("enabled", True) is False:
            continue
        try:
            v_piece = _evaluate_piece(piece, X, Y)
            V += v_piece
        except Exception as e:
            raise ValueError(f"Error evaluando pieza #{i} ({piece.get('label', piece.get('op'))}):\n{e}")
    return V


def _evaluate_piece(piece: dict, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Evalúa una sola pieza recursivamente."""
    op = piece.get("op")
    if op is None:
        raise ValueError(f"Pieza sin 'op': {piece}")

    # --- operaciones compuestas ---
    if op == "mask":
        region_arr = _evaluate_region(piece["region"], X, Y)
        value = piece.get("value", 0.0)
        return op_mask(region_arr, value)

    if op == "where":
        region_arr = _evaluate_region(piece["region"], X, Y)
        V_in  = _evaluate_piece(piece["inner"], X, Y)
        V_out = _evaluate_piece(piece["outer"], X, Y)
        return op_where(region_arr, V_in, V_out)

    if op == "clamp":
        V = _evaluate_piece(piece["inner"], X, Y)
        return op_clamp(V, piece.get("V_min", -np.inf), piece.get("V_max", np.inf))

    if op == "scale":
        V = _evaluate_piece(piece["inner"], X, Y)
        return V * float(piece.get("factor", 1.0))

    if op == "sum":
        pieces = piece.get("pieces", [])
        V = np.zeros(X.shape, dtype=float)
        for sub in pieces:
            V += _evaluate_piece(sub, X, Y)
        return V

    # --- primitivas registradas ---
    if op in PROFILE_PRIMITIVES:
        spec = PROFILE_PRIMITIVES[op]
        args = {**spec.args, **piece.get("args", {})}
        # Conversión: center si viene como tupla/list, OK; vertices etc también
        return spec.fn(X, Y, **args).astype(float)

    if op in REGION_PRIMITIVES:
        raise ValueError(
            f"'{op}' es una REGIÓN; debe usarse dentro de 'mask' o 'where'. "
            f"Recibido como pieza independiente."
        )

    raise ValueError(f"Operación desconocida: '{op}'")


def _evaluate_region(region_piece: dict, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Evalúa una región (debe ser primitiva REGION o composición de regiones)."""
    op = region_piece.get("op")

    if op == "union":
        regs = [_evaluate_region(r, X, Y) for r in region_piece.get("regions", [])]
        out = np.zeros(X.shape, dtype=bool)
        for r in regs:
            out |= r
        return out

    if op == "intersection":
        regs = [_evaluate_region(r, X, Y) for r in region_piece.get("regions", [])]
        out = np.ones(X.shape, dtype=bool)
        for r in regs:
            out &= r
        return out

    if op == "complement":
        return ~_evaluate_region(region_piece["region"], X, Y)

    if op in REGION_PRIMITIVES:
        spec = REGION_PRIMITIVES[op]
        args = {**spec.args, **region_piece.get("args", {})}
        return spec.fn(X, Y, **args).astype(bool)

    raise ValueError(f"Región desconocida: '{op}'. "
                     f"Disponibles: {list(REGION_PRIMITIVES)} + union/intersection/complement")


# ---------------------------------------------------------------------------
# Conversión Design → expresión MATLAB (para exportar a COMSOL)
# ---------------------------------------------------------------------------

def _param_unit_for_expr(name: str) -> str:
    n = name.lower()
    if n in {"n", "k", "cycles", "ciclos", "nfoot", "nshape", "nexp"}:
        return ""
    if n in {"theta", "phi"} or "angle" in n or n.endswith("deg"):
        return "deg"
    if n.startswith("v") or any(t in n for t in ("depth", "amp", "height", "value", "pot", "barrier")):
        return "eV"
    return "nm"


def design_to_matlab_expr(design: dict) -> str:
    """
    Convierte un Design a una expresión MATLAB/COMSOL en coordenadas (x,y)
    en METROS (no nm — COMSOL usa SI).

    Retorna un string como:
      "-0.3*exp(-((x-0)^2+(y-0)^2)/(2*(20e-9)^2)) + 0.5*((sqrt((x-15e-9)^2+y^2) < 5e-9))"
    """
    terms = []
    params = design.get("parameters") or {}
    for piece in design.get("pieces", []):
        if piece.get("enabled", True) is False:
            continue
        terms.append(_piece_to_matlab(piece, params))
    return " + ".join(terms) if terms else "0"


def _matlab_length(value) -> str:
    """Length expression in SI, preserving COMSOL parameters that already carry units."""
    return f"({value})" if isinstance(value, str) else f"({value}e-9)"


def _matlab_scaled(value, numeric_scale: float) -> str:
    """Scale legacy unitless numbers, but leave named unit-bearing parameters intact."""
    return f"({value})" if isinstance(value, str) else f"({value}*{numeric_scale:g})"


def _piece_to_matlab(piece: dict, params: dict | None = None) -> str:
    op = piece.get("op")

    # Helpers
    def nm(v):
        """Convierte nm a notación e-9 de MATLAB."""
        if isinstance(v, (list, tuple)):
            return [f"{x}e-9" for x in v]
        return f"{v}e-9"

    if op == "constant":
        return f"({piece['args']['value']})"

    if op == "gaussian":
        c = piece["args"]["center"]
        amp = piece["args"]["amplitude"]
        sig = piece["args"]["sigma"]
        return (f"({amp})*exp(-((x-{_matlab_length(c[0])})^2+(y-{_matlab_length(c[1])})^2)"
                f"/(2*{_matlab_length(sig)}^2))")

    if op == "mexican_hat":
        c = piece["args"]["center"]
        r0 = piece["args"]["r0"]
        d = piece["args"]["depth"]
        return (f"({d})*((sqrt((x-{_matlab_length(c[0])})^2+(y-{_matlab_length(c[1])})^2))^2"
                f"-{_matlab_length(r0)}^2)^2/({_matlab_length(r0)}^4) - ({d})")

    if op == "harmonic_2d":
        c = piece["args"]["center"]
        w = piece["args"]["omega_eV"]
        return (f"0.5*{_matlab_scaled(w, 1e18)}*"
                f"((x-{_matlab_length(c[0])})^2+(y-{_matlab_length(c[1])})^2)")
        # Nota: omega_eV está en eV/nm², convertido a eV/m² → ×1e18

    if op == "linear":
        sl = piece["args"]["slope"]
        ax = piece["args"]["axis"]
        off = piece["args"].get("offset", 0.0)
        return f"{_matlab_scaled(sl, 1e9)}*{ax} + ({off})"   # slope eV/nm → eV/m

    if op == "coulomb":
        c = piece["args"]["center"]
        q = piece["args"]["charge"]
        eps = piece["args"]["eps_r"]
        reg = piece["args"].get("regularization", 1.0)
        return (f"-{q}*1.439964e-9/({eps}*"
                f"sqrt((x-{_matlab_length(c[0])})^2+(y-{_matlab_length(c[1])})^2+"
                f"{_matlab_length(reg)}^2))")

    if op == "raw_expr":
        # raw_expr se evalúa internamente con x,y en nm; COMSOL recibe x,y en m.
        params = params or {}
        expr = piece["args"]["expr"].replace("**", "^")
        expr = re.sub(r"\bx\b", "(x/(1[nm]))", expr)
        expr = re.sub(r"\by\b", "(y/(1[nm]))", expr)
        expr = re.sub(r"\br\b", "(sqrt(x^2+y^2)/(1[nm]))", expr)
        expr = re.sub(r"\btheta\b", "atan2(y,x)", expr)
        for name in sorted(params, key=len, reverse=True):
            unit = _param_unit_for_expr(name)
            if unit == "nm":
                repl = f"({name}/(1[nm]))"
            elif unit == "deg":
                repl = f"({name}/(1[deg]))"
            else:
                repl = name
            expr = re.sub(rf"\b{re.escape(name)}\b", repl, expr)
        return "(" + expr + ")"

    if op == "mask":
        reg = _region_to_matlab(piece["region"])
        val = piece.get("value", 0.0)
        return f"({val})*({reg})"

    raise ValueError(
        f"La primitiva 2D '{op}' no tiene una traducción analítica equivalente a COMSOL."
    )


def _region_to_matlab(region: dict) -> str:
    """Región → expresión booleana MATLAB (0/1)."""
    op = region.get("op")
    if op == "disk":
        c = region["args"]["center"]
        r = region["args"]["radius"]
        return f"((sqrt((x-({c[0]}e-9))^2+(y-({c[1]}e-9))^2)) <= ({r}e-9))"
    if op == "rectangle":
        c = region["args"]["center"]
        Lx = region["args"]["Lx"]; Ly = region["args"]["Ly"]
        ang = region["args"].get("angle_deg", 0.0)
        cx, cy = f"({c[0]}e-9)", f"({c[1]}e-9)"
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a}*(x-{cx}) + {sin_a}*(y-{cy}))"
            dy = f"(-{sin_a}*(x-{cx}) + {cos_a}*(y-{cy}))"
        else:
            dx = f"(x-{cx})"
            dy = f"(y-{cy})"
        return f"((abs({dx}) <= ({Lx/2}e-9)) & (abs({dy}) <= ({Ly/2}e-9)))"
    if op == "annulus":
        c = region["args"]["center"]
        ri = region["args"]["r_inner"]; ro = region["args"]["r_outer"]
        return (f"((sqrt((x-({c[0]}e-9))^2+(y-({c[1]}e-9))^2) >= ({ri}e-9)) & "
                f"(sqrt((x-({c[0]}e-9))^2+(y-({c[1]}e-9))^2) <= ({ro}e-9)))")
    if op == "ellipse":
        c = region["args"]["center"]
        a_val = region["args"]["a"]
        b_val = region["args"]["b"]
        ang = region["args"].get("angle_deg", 0.0)
        cx, cy = f"({c[0]}e-9)", f"({c[1]}e-9)"
        a_str, b_str = f"({a_val}e-9)", f"({b_val}e-9)"
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a}*(x-{cx}) + {sin_a}*(y-{cy}))"
            dy = f"(-{sin_a}*(x-{cx}) + {cos_a}*(y-{cy}))"
        else:
            dx = f"(x-{cx})"
            dy = f"(y-{cy})"
        return f"((({dx}/{a_str})^2 + ({dy}/{b_str})^2) <= 1.0)"
    if op == "super_ellipse":
        c = region["args"]["center"]
        a_val = region["args"]["a"]
        b_val = region["args"]["b"]
        n_val = region["args"]["n"]
        ang = region["args"].get("angle_deg", 0.0)
        cx, cy = f"({c[0]}e-9)", f"({c[1]}e-9)"
        a_str, b_str = f"({a_val}e-9)", f"({b_val}e-9)"
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a}*(x-{cx}) + {sin_a}*(y-{cy}))"
            dy = f"(-{sin_a}*(x-{cx}) + {cos_a}*(y-{cy}))"
        else:
            dx = f"(x-{cx})"
            dy = f"(y-{cy})"
        return f"(((abs({dx}/{a_str}))^{n_val} + (abs({dy}/{b_str}))^{n_val}) <= 1.000000000001)"
    if op == "rose":
        c = region["args"]["center"]
        k_val = region["args"]["k"]
        R_val = region["args"]["R"]
        ang = region["args"].get("angle_deg", 0.0)
        cx, cy = f"({c[0]}e-9)", f"({c[1]}e-9)"
        R_str = f"({R_val}e-9)"
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a}*(x-{cx}) + {sin_a}*(y-{cy}))"
            dy = f"(-{sin_a}*(x-{cx}) + {cos_a}*(y-{cy}))"
        else:
            dx = f"(x-{cx})"
            dy = f"(y-{cy})"
        return f"(sqrt({dx}^2 + {dy}^2) <= {R_str} * abs(cos({k_val} * atan2({dy}, {dx}))))"
    if op == "half_plane":
        coord = region["args"]["axis"]
        pos = region["args"]["position"]
        side = region["args"]["side"]
        comp = ">=" if side == "positive" else "<="
        return f"({coord} {comp} ({pos}e-9))"
    if op == "union":
        regs = [_region_to_matlab(r) for r in region.get("regions", [])]
        return "(" + " | ".join(regs) + ")" if regs else "0"
    if op == "intersection":
        regs = [_region_to_matlab(r) for r in region.get("regions", [])]
        return "(" + " & ".join(regs) + ")" if regs else "1"
    if op == "complement":
        reg = _region_to_matlab(region["region"])
        return f"(!({reg}))"
    return "1"


# ---------------------------------------------------------------------------
# Conversión: catálogo viejo → Design (para que presets sigan funcionando)
# ---------------------------------------------------------------------------

def preset_to_design(pot_name: str, params: dict, dim: int = 2) -> dict:
    """
    Convierte un preset del catálogo viejo (quantum_dot, quantum_ring, etc.)
    a un Design equivalente con primitivas.
    """
    if dim == 2:
        return _preset_2d(pot_name, params)
    else:
        return _preset_1d(pot_name, params)


def _preset_2d(name: str, p: dict) -> dict:
    from .potentials import POTENTIALS

    if name not in POTENTIALS:
        raise ValueError(f"Preset 2D desconocido: '{name}'. Disponibles: {', '.join(POTENTIALS)}")

    provided = dict(p)
    p = {**POTENTIALS[name].params, **provided}
    if name == "quantum_dot" and "radius" in provided and "sigma" not in provided:
        p["sigma"] = p["radius"]

    pieces = []
    if name == "quantum_dot":
        pieces = [{
            "op": "gaussian",
            "args": {"center":[p.get("offset_x",0), p.get("offset_y",0)],
                     "amplitude": -p["depth"], "sigma": p["sigma"]},
            "label": "punto cuántico",
        }]
    elif name == "quantum_ring":
        pieces = [{
            "op": "mexican_hat",
            "args": {"center":[0,0], "r0": p["r0"], "depth": p["depth"]},
            "label": "anillo cuántico",
        }]
    elif name == "double_dot":
        s = p["separation"] / 2
        pieces = [
            {"op":"gaussian",
             "args":{"center":[-s,0],"amplitude":-p["depth"],"sigma":p["sigma"]},
             "label":"punto izquierdo"},
            {"op":"gaussian",
             "args":{"center":[s,0],"amplitude":-p["depth"],"sigma":p["sigma"]},
             "label":"punto derecho"},
        ]
    elif name == "harmonic":
        pieces = [{
            "op":"harmonic_2d",
            "args":{"center":[p.get("offset_x",0), p.get("offset_y",0)],
                    "omega_eV": p["omega_eV"]},
            "label":"oscilador armónico",
        }]
    elif name == "triple_dot":
        import numpy as np
        angles = [0, 2*np.pi/3, 4*np.pi/3]
        pieces = []
        for i, a in enumerate(angles):
            cx = p["r_triangle"] * np.cos(a)
            cy = p["r_triangle"] * np.sin(a)
            pieces.append({
                "op":"gaussian",
                "args":{"center":[float(cx),float(cy)],
                        "amplitude":-p["depth"],"sigma":p["sigma"]},
                "label":f"punto {i+1}",
            })
    return {"dim": 2, "pieces": pieces}


def _preset_1d(name: str, p: dict) -> dict:
    """Convierte preset del catálogo legacy 1D a Design DSL 1D."""
    from .potentials_1d import POTENTIALS_1D

    if name not in POTENTIALS_1D:
        raise ValueError(f"Preset 1D desconocido: '{name}'. Disponibles: {', '.join(POTENTIALS_1D)}")

    p = {**POTENTIALS_1D[name].params, **p}

    if name == "finite_well":
        return {"dim": 1, "pieces": [
            {"op": "mask",
             "region": {"op": "interval", "args": {"center":0, "length":p["L"]}},
             "value": -p["depth"], "label": "pozo finito"},
        ]}
    if name == "infinite_well":
        L = p["L"]
        return {"dim": 1, "pieces": [
            {"op":"infinite_wall","args":{"position":-L/2,"side":"left"},"label":"pared izq"},
            {"op":"infinite_wall","args":{"position": L/2,"side":"right"},"label":"pared der"},
        ]}
    if name == "harmonic":
        return {"dim": 1, "pieces": [
            {"op":"harmonic","args":{"center":p.get("offset",0),"omega_eV":p["omega_eV"]},
             "label":"oscilador armónico"},
        ]}
    if name == "double_well":
        s = p["separation"]/2
        return {"dim": 1, "pieces": [
            {"op":"gaussian","args":{"center":-s,"amplitude":-p["depth"],"sigma":p["sigma"]},
             "label":"pozo izquierdo"},
            {"op":"gaussian","args":{"center": s,"amplitude":-p["depth"],"sigma":p["sigma"]},
             "label":"pozo derecho"},
        ]}
    if name == "barrier":
        return {"dim": 1, "pieces": [
            {"op":"barrier","args":{"center":p.get("offset",0),"height":p["height"],"width":p["width"]},
             "label":"barrera"},
        ]}
    if name == "morse":
        return {"dim": 1, "pieces": [
            {"op":"morse","args":{"De":p["De"],"a":p["a"],"x0":p["x0"]},"label":"Morse"},
        ]}
    if name == "poschl_teller":
        return {"dim": 1, "pieces": [
            {"op":"poschl_teller","args":{"center":0,"depth":p["depth"],"alpha":p["alpha"]},
             "label":"Pöschl-Teller"},
        ]}
    if name == "triangular":
        return {"dim": 1, "pieces": [
            {"op":"triangular","args":{"slope":p["force"],"x_wall":p["x_wall"]},
             "label":"triangular Stark"},
        ]}
    if name == "gaussian_well":
        return {"dim": 1, "pieces": [
            {"op":"gaussian","args":{"center":p.get("offset",0),
                                       "amplitude":-p["depth"],"sigma":p["sigma"]},
             "label":"pozo gaussiano"},
        ]}
    if name == "step":
        return {"dim": 1, "pieces": [
            {"op":"step","args":{"position":p.get("offset",0),"height":p["height"]},
             "label":"escalón"},
        ]}
    raise ValueError(f"Preset 1D no implementado: '{name}'")


# ===========================================================================
# COMPOSER 1D
# ===========================================================================

def evaluate_design_1d(design: dict, x: np.ndarray) -> np.ndarray:
    """Evalúa Design 1D sobre la grilla x (en nm) → V en eV."""
    V = np.zeros_like(x, dtype=float)
    for i, piece in enumerate(design.get("pieces", [])):
        if piece.get("enabled", True) is False:
            continue
        try:
            V += _evaluate_piece_1d(piece, x)
        except Exception as e:
            raise ValueError(f"Error evaluando pieza 1D #{i} "
                              f"({piece.get('label', piece.get('op'))}):\n{e}")
    return V


def _evaluate_piece_1d(piece: dict, x: np.ndarray) -> np.ndarray:
    op = piece.get("op")
    if op is None:
        raise ValueError(f"Pieza sin 'op': {piece}")

    if op == "mask":
        region_arr = _evaluate_region_1d(piece["region"], x)
        value = piece.get("value", 0.0)
        out = np.zeros_like(x, dtype=float)
        out[region_arr] = value if np.isscalar(value) else value[region_arr]
        return out

    if op == "where":
        region_arr = _evaluate_region_1d(piece["region"], x)
        V_in  = _evaluate_piece_1d(piece["inner"], x)
        V_out = _evaluate_piece_1d(piece["outer"], x)
        return np.where(region_arr, V_in, V_out)

    if op == "clamp":
        V = _evaluate_piece_1d(piece["inner"], x)
        return np.clip(V, piece.get("V_min", -np.inf), piece.get("V_max", np.inf))

    if op == "scale":
        V = _evaluate_piece_1d(piece["inner"], x)
        return V * float(piece.get("factor", 1.0))

    if op in PROFILE_PRIMITIVES_1D:
        spec = PROFILE_PRIMITIVES_1D[op]
        args = {**spec.args, **piece.get("args", {})}
        return spec.fn(x, **args).astype(float)

    if op in REGION_PRIMITIVES_1D:
        raise ValueError(f"'{op}' es región 1D; debe usarse dentro de mask/where.")

    raise ValueError(f"Operación 1D desconocida: '{op}'")


def _evaluate_region_1d(region_piece: dict, x: np.ndarray) -> np.ndarray:
    op = region_piece.get("op")
    if op == "union":
        out = np.zeros_like(x, dtype=bool)
        for r in region_piece.get("regions", []):
            out |= _evaluate_region_1d(r, x)
        return out
    if op == "intersection":
        out = np.ones_like(x, dtype=bool)
        for r in region_piece.get("regions", []):
            out &= _evaluate_region_1d(r, x)
        return out
    if op == "complement":
        return ~_evaluate_region_1d(region_piece["region"], x)
    if op in REGION_PRIMITIVES_1D:
        spec = REGION_PRIMITIVES_1D[op]
        args = {**spec.args, **region_piece.get("args", {})}
        return spec.fn(x, **args).astype(bool)
    raise ValueError(f"Región 1D desconocida: '{op}'.")


def design_to_matlab_expr_1d(design: dict) -> str:
    """Design 1D → expresión MATLAB en coordenada x (en metros)."""
    terms = []
    for piece in design.get("pieces", []):
        if piece.get("enabled", True) is False:
            continue
        terms.append(_piece_to_matlab_1d(piece, design.get("parameters") or {}))
    return " + ".join(terms) if terms else "0"


def _piece_to_matlab_1d(piece: dict, params: dict | None = None) -> str:
    op = piece.get("op")
    a = piece.get("args", {})

    if op == "constant": return f"({a['value']})"

    if op == "gaussian":
        return (f"({a['amplitude']})*exp(-(x-{_matlab_length(a['center'])})^2"
                f"/(2*{_matlab_length(a['sigma'])}^2))")

    if op == "harmonic":
        # omega_eV en eV/nm² → eV/m²: ×1e18
        return (f"0.5*{_matlab_scaled(a['omega_eV'], 1e18)}*"
                f"(x-{_matlab_length(a['center'])})^2")

    if op == "coulomb":
        return (f"-{a['charge']}*1.439964e-9/({a['eps_r']}*"
                f"sqrt((x-{_matlab_length(a['center'])})^2+"
                f"{_matlab_length(a['regularization'])}^2))")

    if op == "linear":
        return f"{_matlab_scaled(a['slope'], 1e9)}*x + ({a.get('offset',0)})"

    if op == "exp_decay":
        return (f"({a['amplitude']})*exp(-abs(x-{_matlab_length(a['center'])})/"
                f"{_matlab_length(a['length'])})")

    if op == "poschl_teller":
        # alpha en nm⁻¹ → m⁻¹: ×1e9
        return (f"-({a['depth']})/cosh({_matlab_scaled(a['alpha'], 1e9)}*"
                f"(x-{_matlab_length(a['center'])}))^2")

    if op == "morse":
        return (f"({a['De']})*(1-exp(-{_matlab_scaled(a['a'], 1e9)}*"
                f"(x-{_matlab_length(a['x0'])})))^2 - ({a['De']})")

    if op == "step":
        return f"({a['height']})*(x>={_matlab_length(a['position'])})"

    if op == "barrier":
        half_width = (f"({a['width']})/2" if isinstance(a['width'], str)
                      else _matlab_length(a['width'] / 2))
        return (f"({a['height']})*(abs(x-{_matlab_length(a['center'])}) <= {half_width})")

    if op == "infinite_wall":
        cmp = "<=" if a.get("side", "left") == "left" else ">="
        return f"({a.get('V_inf', 1000.0)})*(x {cmp} {_matlab_length(a['position'])})"

    if op == "triangular":
        wall = _matlab_length(a["x_wall"])
        slope = _matlab_scaled(a["slope"], 1e9)
        return (f"if(x<={wall},({a.get('V_inf', 1000.0)}),"
                f"{slope}*(x-{wall}))")

    if op == "raw_expr":
        expr = a["expr"].replace("**", "^")
        expr = re.sub(r"\bx\b", "(x/(1[nm]))", expr)
        for name in sorted(params or {}, key=len, reverse=True):
            unit = _param_unit_for_expr(name)
            repl = f"({name}/(1[{unit}]))" if unit in {"nm", "deg"} else name
            expr = re.sub(rf"\b{re.escape(name)}\b", repl, expr)
        return "(" + expr + ")"

    if op == "mask":
        return f"({piece.get('value',0)})*({_region_to_matlab_1d(piece['region'])})"

    raise ValueError(
        f"La primitiva 1D '{op}' no tiene una traducción analítica equivalente a COMSOL."
    )


def _region_to_matlab_1d(region: dict) -> str:
    op = region.get("op")
    a = region.get("args", {})
    if op == "interval":
        half_length = (f"({_matlab_length(a['length'])})/2"
                       if isinstance(a["length"], str)
                       else _matlab_length(a["length"] / 2))
        return f"(abs(x-{_matlab_length(a['center'])}) <= {half_length})"
    if op == "half_line":
        cmp = ">=" if a.get("side","positive") == "positive" else "<="
        return f"(x {cmp} {_matlab_length(a['position'])})"
    if op == "strip":
        return (f"((x>={_matlab_length(a['x_min'])}) & "
                f"(x<={_matlab_length(a['x_max'])}))")
    raise ValueError(f"La región 1D '{op}' no tiene traducción equivalente a COMSOL.")


def generate_comsol_recipe(design: dict) -> str:
    dim = design.get("dim", 2)
    L_nm = design.get("domain", {}).get("L", 200.0 if dim == 2 else 120.0)
    
    # 1. Parámetros
    params = {}
    params["L"] = (f"{L_nm}", "nm", "Tamaño del dominio de simulación")
    
    # Expresión paramétrica
    expr_parts = []
    
    pieces = design.get("pieces", [])
    for i, piece in enumerate(pieces):
        if piece.get("enabled", True) is False:
            continue
        
        lbl = piece.get("label", f"pieza_{i+1}")
        op = piece.get("op")
        
        # Generar sufijo único para parámetros de esta pieza
        suf = f"_{i+1}"
        
        if op == "constant":
            v = piece["args"]["value"]
            params[f"V{suf}"] = (f"{v}", "eV", f"Valor constante para {lbl}")
            expr_parts.append(f"V{suf}")
            
        elif op == "gaussian":
            amp = piece["args"]["amplitude"]
            sig = piece["args"]["sigma"]
            params[f"V{suf}"] = (f"{amp}", "eV", f"Amplitud de la gaussiana {lbl}")
            params[f"sig{suf}"] = (f"{sig}", "nm", f"Ancho sigma de {lbl}")
            
            if dim == 1:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c}", "nm", f"Centro x de {lbl}")
                expr_parts.append(f"V{suf} * exp(-(x - cx{suf})^2 / (2 * sig{suf}^2))")
            else:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c[0]}", "nm", f"Centro x de {lbl}")
                params[f"cy{suf}"] = (f"{c[1]}", "nm", f"Centro y de {lbl}")
                expr_parts.append(f"V{suf} * exp(-((x - cx{suf})^2 + (y - cy{suf})^2) / (2 * sig{suf}^2))")
                
        elif op == "mexican_hat":
            depth = piece["args"]["depth"]
            r0 = piece["args"]["r0"]
            params[f"V{suf}"] = (f"-{depth}", "eV", f"Profundidad mínima de {lbl}")
            params[f"r0{suf}"] = (f"{r0}", "nm", f"Radio del mínimo de {lbl}")
            
            c = piece["args"]["center"]
            params[f"cx{suf}"] = (f"{c[0]}", "nm", f"Centro x de {lbl}")
            params[f"cy{suf}"] = (f"{c[1]}", "nm", f"Centro y de {lbl}")
            
            expr_parts.append(f"-V{suf} * (((x - cx{suf})^2 + (y - cy{suf})^2 - r0{suf}^2)^2 / r0{suf}^4) + V{suf}")
            
        elif op == "coulomb":
            q = piece["args"]["charge"]
            eps = piece["args"]["eps_r"]
            reg = piece["args"].get("regularization", 1.0)
            
            params[f"q{suf}"] = (f"{q}", "e", f"Carga de impureza {lbl}")
            params[f"eps{suf}"] = (f"{eps}", "", f"Constante dieléctrica para {lbl}")
            params[f"reg{suf}"] = (f"{reg}", "nm", f"Radio de regularización para {lbl}")
            
            k_c = "1.439964" # eV*nm
            
            if dim == 1:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c}", "nm", f"Centro x de {lbl}")
                expr_parts.append(f"-q{suf} * {k_c} / (eps{suf} * sqrt((x - cx{suf})^2 + reg{suf}^2))")
            else:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c[0]}", "nm", f"Centro x de {lbl}")
                params[f"cy{suf}"] = (f"{c[1]}", "nm", f"Centro y de {lbl}")
                expr_parts.append(f"-q{suf} * {k_c} / (eps{suf} * sqrt((x - cx{suf})^2 + (y - cy{suf})^2 + reg{suf}^2))")
                
        elif op == "harmonic" or op == "harmonic_2d":
            w = piece["args"]["omega_eV"]
            params[f"w{suf}"] = (f"{w}", "eV/nm^2", f"Curvatura armónica para {lbl}")
            
            if dim == 1:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c}", "nm", f"Centro x de {lbl}")
                expr_parts.append(f"0.5 * w{suf} * (x - cx{suf})^2")
            else:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c[0]}", "nm", f"Centro x de {lbl}")
                params[f"cy{suf}"] = (f"{c[1]}", "nm", f"Centro y de {lbl}")
                expr_parts.append(f"0.5 * w{suf} * ((x - cx{suf})^2 + (y - cy{suf})^2)")
                
        elif op == "linear":
            sl = piece["args"]["slope"]
            off = piece["args"].get("offset", 0.0)
            params[f"slope{suf}"] = (f"{sl}", "eV/nm", f"Pendiente del campo para {lbl}")
            params[f"off{suf}"] = (f"{off}", "eV", f"Offset para {lbl}")
            
            if dim == 1:
                expr_parts.append(f"slope{suf} * x + off{suf}")
            else:
                ax = piece["args"]["axis"]
                expr_parts.append(f"slope{suf} * {ax} + off{suf}")
                
        elif op == "poschl_teller":
            depth = piece["args"]["depth"]
            alpha = piece["args"]["alpha"]
            params[f"V{suf}"] = (f"{depth}", "eV", f"Profundidad de Pöschl-Teller {lbl}")
            params[f"alpha{suf}"] = (f"{alpha}", "1/nm", f"Inverso del ancho para {lbl}")
            
            if dim == 1:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c}", "nm", f"Centro x de {lbl}")
                expr_parts.append(f"-V{suf} / (cosh(alpha{suf} * (x - cx{suf})))^2")
            else:
                c = piece["args"]["center"]
                params[f"cx{suf}"] = (f"{c[0]}", "nm", f"Centro x de {lbl}")
                params[f"cy{suf}"] = (f"{c[1]}", "nm", f"Centro y de {lbl}")
                expr_parts.append(f"-V{suf} / (cosh(alpha{suf} * sqrt((x - cx{suf})^2 + (y - cy{suf})^2)))^2")
                
        elif op == "morse":
            De = piece["args"]["De"]
            a_val = piece["args"]["a"]
            x0 = piece["args"]["x0"]
            params[f"De{suf}"] = (f"{De}", "eV", f"Energía de disociación de Morse {lbl}")
            params[f"a{suf}"] = (f"{a_val}", "1/nm", f"Ancho de Morse para {lbl}")
            params[f"x0{suf}"] = (f"{x0}", "nm", f"Posición de equilibrio x0 para {lbl}")
            
            expr_parts.append(f"De{suf} * (1 - exp(-a{suf} * (x - x0{suf})))^2 - De{suf}")
            
        elif op == "step":
            h = piece["args"]["height"]
            pos = piece["args"]["position"]
            params[f"h{suf}"] = (f"{h}", "eV", f"Altura del escalón {lbl}")
            params[f"pos{suf}"] = (f"{pos}", "nm", f"Posición del escalón {lbl}")
            
            expr_parts.append(f"h{suf} * (x >= pos{suf})")
            
        elif op == "barrier":
            h = piece["args"]["height"]
            w = piece["args"]["width"]
            c = piece["args"]["center"]
            params[f"h{suf}"] = (f"{h}", "eV", f"Altura de la barrera {lbl}")
            params[f"w{suf}"] = (f"{w}", "nm", f"Ancho de la barrera {lbl}")
            params[f"cx{suf}"] = (f"{c}", "nm", f"Centro x de {lbl}")
            
            expr_parts.append(f"h{suf} * (abs(x - cx{suf}) <= w{suf}/2)")
            
        elif op == "mask":
            val = piece.get("value", 0.0)
            params[f"V{suf}"] = (f"{val}", "eV", f"Valor del potencial para {lbl}")
            
            reg_expr, reg_params = _region_to_parameterized_expr(piece["region"], suf, params)
            expr_parts.append(f"V{suf} * ({reg_expr})")
            
        elif op == "where":
            reg_expr, reg_params = _region_to_parameterized_expr(piece["region"], suf, params)
            v_in = piece["inner"].get("args", {}).get("value", -0.3)
            v_out = piece["outer"].get("args", {}).get("value", 0.0)
            params[f"Vin{suf}"] = (f"{v_in}", "eV", f"Valor interno para {lbl}")
            params[f"Vout{suf}"] = (f"{v_out}", "eV", f"Valor externo para {lbl}")
            
            expr_parts.append(f"( {reg_expr} ) * Vin{suf} + (1 - ({reg_expr})) * Vout{suf}")
            
        elif op == "raw_expr":
            expr = piece["args"]["expr"]
            expr_parts.append(f"({expr})")
            
    # Ensamblar markdown
    md = []
    md.append("### 📋 Receta de Configuración de COMSOL Paso a Paso\n")
    md.append("Puedes usar esta receta para reconstruir el potencial **manualmente** en tu COMSOL de escritorio, con control total sobre los parámetros físicos.\n")
    
    md.append("#### 1️⃣ Definir Parámetros Globales")
    md.append("Ve a **Global Definitions -> Parameters 1** y agrega la siguiente tabla de parámetros:")
    md.append("\n| Nombre | Expresión | Valor / Unidad | Descripción |")
    md.append("|---|---|---|---|")
    for name, (val, unit, desc) in params.items():
        val_unit = f"{val}[{unit}]" if unit else f"{val}"
        md.append(f"| `{name}` | `{val_unit}` | | {desc} |")
    md.append("\n")
    
    md.append("#### 2️⃣ Configurar la Geometría")
    if dim == 1:
        md.append("1. Agrega una geometría **1D** (`geom1`).")
        md.append("2. En **Geometry 1**, crea un **Interval** (`i1`).")
        md.append("3. Configura sus coordenadas:\n   - **p1:** `-L/2`\n   - **p2:** `L/2`\n   - Haz clic en **Build Selected** o **Build All**.")
    else:
        md.append("1. Agrega una geometría **2D** (`geom1`).")
        md.append("2. En **Geometry 1**, crea un **Rectangle** (`r1`).")
        md.append("3. Configura sus propiedades:\n   - **Width (lx):** `L`\n   - **Height (ly):** `L`\n   - **Base:** `Center`\n   - Haz clic en **Build Selected** o **Build All**.")
    md.append("\n")
    
    md.append("#### 3️⃣ Agregar la Función del Potencial")
    md.append("1. Ve a **Global Definitions -> Functions** y agrega una función **Analytic** (`V_pot`).")
    md.append("2. Configura los siguientes campos:")
    md.append(f"   - **Function name:** `V_pot`")
    args_str = "x" if dim == 1 else "x,y"
    argunit_str = "m" if dim == 1 else "m,m"
    md.append(f"   - **Arguments:** `{args_str}`")
    md.append(f"   - **Expression:** (copia y pega la siguiente línea)")
    full_expr = " + ".join(expr_parts) if expr_parts else "0"
    md.append(f"     ```matlab\n     {full_expr}\n     ```")
    md.append(f"   - **Arguments Units:** `{argunit_str}`")
    md.append(f"   - **Function Unit:** `eV`")
    md.append("3. **Límites de Graficación:** En el panel **Plot Parameters**, cambia los límites de visualización de los argumentos:")
    if dim == 1:
        md.append("   - **x:** de `-L/2` a `L/2` o `-100[nm]` a `100[nm]`")
    else:
        md.append("   - **x:** de `-L/2` a `L/2`\n   - **y:** de `-L/2` a `L/2`")
    md.append("\n")
    
    md.append("#### 4️⃣ Configurar la Física y el Estudio")
    md.append("1. Agrega una interfaz **Coefficient Form PDE** (`c`) sobre la Geometría (`geom1`).")
    md.append("2. En la física, configura la variable dependiente a `psi`.")
    md.append("3. En el nodo **Coefficient Form PDE 1** (cfeq1), establece:")
    md.append("   - **Diffusion Coefficient (c):** `hbar^2/(2*m_star)`")
    arg_expr_call = "V_pot(x)*eV" if dim == 1 else "V_pot(x,y)*eV"
    md.append(f"   - **Absorption Coefficient (a):** `{arg_expr_call}`")
    md.append("   - **Mass Coefficient (da):** `1`")
    md.append("4. Agrega una condición de contorno **Dirichlet Boundary** en los bordes exteriores de la geometría y establece el valor a `0`.")
    md.append("5. Crea un **Estudio de Eigenvalores** (`std1`).")
    md.append(f"   - Configura el número de estados (`neigs`) a `{design.get('n_states', 6)}` (o el número deseado).")
    md.append("   - ¡Haz clic en **Compute** y listo!")
    
    return "\n".join(md)


def _region_to_parameterized_expr(region: dict, suf: str, params: dict) -> tuple[str, dict]:
    op = region.get("op")
    if op == "disk":
        c = region["args"]["center"]
        r = region["args"]["radius"]
        params[f"cx{suf}"] = (f"{c[0]}", "nm", "Centro x")
        params[f"cy{suf}"] = (f"{c[1]}", "nm", "Centro y")
        params[f"r{suf}"] = (f"{r}", "nm", "Radio de zona circular")
        return f"sqrt((x - cx{suf})^2 + (y - cy{suf})^2) <= r{suf}", params
        
    elif op == "rectangle":
        c = region["args"]["center"]
        Lx = region["args"]["Lx"]
        Ly = region["args"]["Ly"]
        ang = region["args"].get("angle_deg", 0.0)
        params[f"cx{suf}"] = (f"{c[0]}", "nm", "Centro x")
        params[f"cy{suf}"] = (f"{c[1]}", "nm", "Centro y")
        params[f"Lx{suf}"] = (f"{Lx}", "nm", "Ancho Lx")
        params[f"Ly{suf}"] = (f"{Ly}", "nm", "Alto Ly")
        
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a:.4f}*(x - cx{suf}) + {sin_a:.4f}*(y - cy{suf}))"
            dy = f"(-{sin_a:.4f}*(x - cx{suf}) + {cos_a:.4f}*(y - cy{suf}))"
        else:
            dx = f"(x - cx{suf})"
            dy = f"(y - cy{suf})"
        return f"(abs({dx}) <= Lx{suf}/2) & (abs({dy}) <= Ly{suf}/2)", params
        
    elif op == "annulus":
        c = region["args"]["center"]
        ri = region["args"]["r_inner"]
        ro = region["args"]["r_outer"]
        params[f"cx{suf}"] = (f"{c[0]}", "nm", "Centro x")
        params[f"cy{suf}"] = (f"{c[1]}", "nm", "Centro y")
        params[f"ri{suf}"] = (f"{ri}", "nm", "Radio interior")
        params[f"ro{suf}"] = (f"{ro}", "nm", "Radio exterior")
        return f"(sqrt((x - cx{suf})^2 + (y - cy{suf})^2) >= ri{suf}) & (sqrt((x - cx{suf})^2 + (y - cy{suf})^2) <= ro{suf})", params
        
    elif op == "ellipse":
        c = region["args"]["center"]
        a = region["args"]["a"]
        b = region["args"]["b"]
        ang = region["args"].get("angle_deg", 0.0)
        params[f"cx{suf}"] = (f"{c[0]}", "nm", "Centro x")
        params[f"cy{suf}"] = (f"{c[1]}", "nm", "Centro y")
        params[f"a{suf}"] = (f"{a}", "nm", "Semieje x")
        params[f"b{suf}"] = (f"{b}", "nm", "Semieje y")
        
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a:.4f}*(x - cx{suf}) + {sin_a:.4f}*(y - cy{suf}))"
            dy = f"(-{sin_a:.4f}*(x - cx{suf}) + {cos_a:.4f}*(y - cy{suf}))"
        else:
            dx = f"(x - cx{suf})"
            dy = f"(y - cy{suf})"
        return f"({dx}/a{suf})^2 + ({dy}/b{suf})^2 <= 1.0", params
        
    elif op == "super_ellipse":
        c = region["args"]["center"]
        a = region["args"]["a"]
        b = region["args"]["b"]
        n = region["args"]["n"]
        ang = region["args"].get("angle_deg", 0.0)
        params[f"cx{suf}"] = (f"{c[0]}", "nm", "Centro x")
        params[f"cy{suf}"] = (f"{c[1]}", "nm", "Centro y")
        params[f"a{suf}"] = (f"{a}", "nm", "Semieje x")
        params[f"b{suf}"] = (f"{b}", "nm", "Semieje y")
        params[f"n{suf}"] = (f"{n}", "", "Exponente de super-elipse")
        
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a:.4f}*(x - cx{suf}) + {sin_a:.4f}*(y - cy{suf}))"
            dy = f"(-{sin_a:.4f}*(x - cx{suf}) + {cos_a:.4f}*(y - cy{suf}))"
        else:
            dx = f"(x - cx{suf})"
            dy = f"(y - cy{suf})"
        return f"(abs({dx}/a{suf}))^n{suf} + (abs({dy}/b{suf}))^n{suf} <= 1.0", params
        
    elif op == "rose":
        c = region["args"]["center"]
        k = region["args"]["k"]
        R = region["args"]["R"]
        ang = region["args"].get("angle_deg", 0.0)
        params[f"cx{suf}"] = (f"{c[0]}", "nm", "Centro x")
        params[f"cy{suf}"] = (f"{c[1]}", "nm", "Centro y")
        params[f"k{suf}"] = (f"{k}", "", "Número de pétalos")
        params[f"R{suf}"] = (f"{R}", "nm", "Radio máximo")
        
        if ang != 0.0:
            ang_rad = ang * 3.141592653589793 / 180.0
            cos_a, sin_a = np.cos(ang_rad), np.sin(ang_rad)
            dx = f"({cos_a:.4f}*(x - cx{suf}) + {sin_a:.4f}*(y - cy{suf}))"
            dy = f"(-{sin_a:.4f}*(x - cx{suf}) + {cos_a:.4f}*(y - cy{suf}))"
        else:
            dx = f"(x - cx{suf})"
            dy = f"(y - cy{suf})"
        return f"sqrt({dx}^2 + {dy}^2) <= R{suf} * abs(cos(k{suf} * atan2({dy}, {dx})))", params
        
    elif op == "half_plane":
        coord = region["args"]["axis"]
        pos = region["args"]["position"]
        side = region["args"]["side"]
        params[f"pos{suf}"] = (f"{pos}", "nm", "Posición divisoria")
        comp = ">=" if side == "positive" else "<="
        return f"{coord} {comp} pos{suf}", params
        
    elif op == "interval": # 1D
        c = region["args"]["center"]
        l_val = region["args"]["length"]
        params[f"cx{suf}"] = (f"{c}", "nm", "Centro x")
        params[f"len{suf}"] = (f"{l_val}", "nm", "Largo del intervalo")
        return f"abs(x - cx{suf}) <= len{suf}/2", params
        
    elif op == "half_line": # 1D
        pos = region["args"]["position"]
        side = region["args"].get("side", "positive")
        params[f"pos{suf}"] = (f"{pos}", "nm", "Posición divisoria")
        comp = ">=" if side == "positive" else "<="
        return f"x {comp} pos{suf}", params
        
    elif op == "strip": # 1D
        x_min = region["args"]["x_min"]
        x_max = region["args"]["x_max"]
        params[f"x_min{suf}"] = (f"{x_min}", "nm", "Límite izquierdo")
        params[f"x_max{suf}"] = (f"{x_max}", "nm", "Límite derecho")
        return f"(x >= x_min{suf}) & (x <= x_max{suf})", params
        
    return "1", params
