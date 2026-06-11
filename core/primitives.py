"""
Biblioteca de primitivas paramétricas para potenciales cuánticos.

Cada primitiva es una función pura que recibe coordenadas (X, Y) en nm
y devuelve un array numpy:
  - Si es una REGIÓN: array booleano (True dentro de la región)
  - Si es un PERFIL DE POTENCIAL: array float en eV

Las primitivas se exponen al composer y a la IA a través de PRIMITIVE_SPECS,
que es la fuente única de verdad sobre nombres, argumentos y descripciones.

Coordenadas: x, y en nanómetros.
Potencial: V en eV.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Any


# ---------------------------------------------------------------------------
# REGIONES (devuelven arrays booleanos)
# ---------------------------------------------------------------------------

def region_disk(X, Y, center=(0.0, 0.0), radius=10.0):
    """Disco circular |r - center| <= radius."""
    cx, cy = center
    return (X - cx) ** 2 + (Y - cy) ** 2 <= radius ** 2


def region_annulus(X, Y, center=(0.0, 0.0), r_inner=10.0, r_outer=20.0):
    """Anillo r_inner <= |r - center| <= r_outer."""
    cx, cy = center
    r2 = (X - cx) ** 2 + (Y - cy) ** 2
    return (r2 >= r_inner ** 2) & (r2 <= r_outer ** 2)


def region_rectangle(X, Y, center=(0.0, 0.0), Lx=20.0, Ly=20.0, angle_deg=0.0):
    """Rectángulo centrado, rotado un ángulo."""
    cx, cy = center
    dx, dy = X - cx, Y - cy
    if angle_deg != 0.0:
        a = np.deg2rad(angle_deg)
        c, s = np.cos(a), np.sin(a)
        dx, dy = c * dx + s * dy, -s * dx + c * dy
    return (np.abs(dx) <= Lx / 2) & (np.abs(dy) <= Ly / 2)


def region_ellipse(X, Y, center=(0.0, 0.0), a=15.0, b=10.0, angle_deg=0.0):
    """Elipse (x/a)² + (y/b)² <= 1."""
    cx, cy = center
    dx, dy = X - cx, Y - cy
    if angle_deg != 0.0:
        ang = np.deg2rad(angle_deg)
        c, s = np.cos(ang), np.sin(ang)
        dx, dy = c * dx + s * dy, -s * dx + c * dy
    return (dx / a) ** 2 + (dy / b) ** 2 <= 1.0


def region_super_ellipse(X, Y, center=(0.0, 0.0), a=15.0, b=15.0, n=4.0, angle_deg=0.0):
    """
    Super-elipse |x/a|^n + |y/b|^n <= 1.
      n=2: elipse, n=4: cuadrado redondeado, n→∞: rectángulo,
      n<2: estrella tipo astroide.
    """
    cx, cy = center
    dx, dy = X - cx, Y - cy
    if angle_deg != 0.0:
        ang = np.deg2rad(angle_deg)
        c, s = np.cos(ang), np.sin(ang)
        dx, dy = c * dx + s * dy, -s * dx + c * dy
    eps = 1e-12
    return (np.abs(dx / a) ** n + np.abs(dy / b) ** n) <= 1.0 + eps


def region_rose(X, Y, center=(0.0, 0.0), k=4, R=20.0, angle_deg=0.0):
    """
    Roseta r <= R·|cos(k·θ)|.
      k=2: 4 pétalos, k=3: 3 pétalos, k=4: 8 pétalos (par → 2k pétalos).
    """
    cx, cy = center
    dx, dy = X - cx, Y - cy
    if angle_deg != 0.0:
        ang = np.deg2rad(angle_deg)
        c, s = np.cos(ang), np.sin(ang)
        dx, dy = c * dx + s * dy, -s * dx + c * dy
    r = np.sqrt(dx ** 2 + dy ** 2)
    theta = np.arctan2(dy, dx)
    return r <= R * np.abs(np.cos(k * theta))


def region_polygon(X, Y, vertices):
    """
    Polígono arbitrario. vertices: lista de (x, y) en nm.
    Usa ray casting.
    """
    pts = np.asarray(vertices, dtype=float)
    n = len(pts)
    inside = np.zeros(X.shape, dtype=bool)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        cond = ((yi > Y) != (yj > Y)) & \
               (X < (xj - xi) * (Y - yi) / (yj - yi + 1e-30) + xi)
        inside ^= cond
        j = i
    return inside


def region_half_plane(X, Y, axis="x", position=0.0, side="positive"):
    """Semi-plano: side='positive' → coord >= position, 'negative' → <= position."""
    coord = X if axis == "x" else Y
    return (coord >= position) if side == "positive" else (coord <= position)


def region_union(X, Y, regions):
    """Unión booleana de varias regiones (lista de arrays bool ya evaluadas)."""
    out = np.zeros(X.shape, dtype=bool)
    for r in regions:
        out |= r
    return out


def region_intersection(X, Y, regions):
    """Intersección de regiones."""
    out = np.ones(X.shape, dtype=bool)
    for r in regions:
        out &= r
    return out


# ---------------------------------------------------------------------------
# PERFILES DE POTENCIAL (devuelven arrays float en eV)
# ---------------------------------------------------------------------------

def profile_constant(X, Y, value=0.0):
    """V = value en todas partes."""
    return np.full(X.shape, float(value))


def profile_gaussian(X, Y, center=(0.0, 0.0), amplitude=-0.3, sigma=20.0):
    """
    V = amplitude · exp(-r²/(2σ²)).
    amplitude < 0 → pozo, amplitude > 0 → barrera.
    """
    cx, cy = center
    r2 = (X - cx) ** 2 + (Y - cy) ** 2
    return amplitude * np.exp(-r2 / (2 * sigma ** 2))


def profile_mexican_hat(X, Y, center=(0.0, 0.0), r0=30.0, depth=0.3):
    """
    Sombrero mexicano: V = depth · (r² - r₀²)² / r₀⁴ - depth.
    Mínimo en r = r₀ con V = -depth.
    """
    cx, cy = center
    r = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    return depth * (r ** 2 - r0 ** 2) ** 2 / (r0 ** 4) - depth


def profile_harmonic_2d(X, Y, center=(0.0, 0.0), omega_eV=0.0002):
    """V = ½ · omega_eV · r²  (parabólico isótropo)."""
    cx, cy = center
    return 0.5 * omega_eV * ((X - cx) ** 2 + (Y - cy) ** 2)


def profile_harmonic_anisotropic(X, Y, center=(0.0, 0.0),
                                  omega_x=0.0002, omega_y=0.0002):
    """V = ½·ωx·x² + ½·ωy·y²."""
    cx, cy = center
    return 0.5 * (omega_x * (X - cx) ** 2 + omega_y * (Y - cy) ** 2)


def profile_coulomb(X, Y, center=(0.0, 0.0), charge=1.0, eps_r=12.9,
                    regularization=1.0):
    """
    Impureza Coulomb (soft Coulomb regularizado).
      V = -charge · e²/(4πε₀εᵣ) · 1/√((r-r₀)² + a²)
    En eV, con coordenadas en nm. charge en unidades de e (charge=+1 = donante).
    eps_r = constante dieléctrica relativa. regularization = a (nm) evita singularidad.
    """
    cx, cy = center
    r = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2 + regularization ** 2)
    # k·e/(εᵣ) en eV·nm donde k·e ≈ 1.439964 eV·nm
    k_eV_nm = 1.439964
    return -charge * k_eV_nm / (eps_r * r)


def profile_linear(X, Y, slope=0.001, axis="x", offset=0.0):
    """Campo lineal: V = slope·coord + offset  (representa campo eléctrico uniforme)."""
    coord = X if axis == "x" else Y
    return slope * coord + offset


def profile_polynomial(X, Y, coeffs=None, center=(0.0, 0.0)):
    """
    V = Σ_{ij} c_ij · (x-x₀)^i · (y-y₀)^j
    coeffs: lista de dicts {i, j, c}. Ej: [{i:2,j:0,c:0.001},{i:0,j:2,c:0.001}]
    """
    cx, cy = center
    dx, dy = X - cx, Y - cy
    V = np.zeros_like(X)
    if coeffs:
        for term in coeffs:
            i, j, c = term["i"], term["j"], term["c"]
            V += c * (dx ** i) * (dy ** j)
    return V


def profile_exp_decay(X, Y, center=(0.0, 0.0), amplitude=-0.3, length=20.0):
    """V = amplitude · exp(-|r-r₀|/length). Decaimiento exponencial radial."""
    cx, cy = center
    r = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    return amplitude * np.exp(-r / length)


def profile_pöschl_teller(X, Y, center=(0.0, 0.0), depth=0.3, alpha=0.05):
    """V = -depth / cosh²(α · |r - r₀|). Versión radial 2D."""
    cx, cy = center
    r = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    return -depth / np.cosh(alpha * r) ** 2


def profile_raw_expr(X, Y, expr=""):
    """
    Evalúa una expresión sobre la grilla con un parser AST restringido.
    Variables disponibles: x, y, r, theta + constantes pi, e.
    Funciones: sin, cos, tan, exp, log, sqrt, abs, sinh, cosh, tanh,
               where, heaviside, power, minimum, maximum.
    Bloqueado: atributos, subscripts, lambdas, dunders, llamadas fuera de whitelist.
    """
    from .safe_expr import safe_eval, UnsafeExpressionError
    if not expr:
        return np.zeros_like(X)
    r = np.sqrt(X ** 2 + Y ** 2)
    theta = np.arctan2(Y, X)
    variables = {"x": X, "y": Y, "r": r, "theta": theta, "pi": np.pi, "e": np.e}
    functions = {
        "sin": np.sin, "cos": np.cos, "tan": np.tan,
        "exp": np.exp, "log": np.log, "sqrt": np.sqrt,
        "abs": np.abs, "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
        "where": np.where, "heaviside": lambda a: np.heaviside(a, 0.5),
        "power": np.power, "minimum": np.minimum, "maximum": np.maximum,
    }
    try:
        return np.asarray(safe_eval(expr, variables, functions), dtype=float)
    except UnsafeExpressionError as e:
        raise ValueError(f"raw_expr rechazada por sandbox: {expr}\n{e}") from e
    except Exception as e:
        raise ValueError(f"raw_expr inválida: {expr}\n{e}") from e


# ---------------------------------------------------------------------------
# OPERACIONES SOBRE PIEZAS
# ---------------------------------------------------------------------------

def op_mask(region_arr: np.ndarray, value: float | np.ndarray) -> np.ndarray:
    """value dentro de la región, 0 fuera."""
    out = np.zeros(region_arr.shape, dtype=float)
    out[region_arr] = value if np.isscalar(value) else value[region_arr]
    return out


def op_where(region_arr: np.ndarray, V_inside: np.ndarray, V_outside: np.ndarray) -> np.ndarray:
    """V_inside donde region, V_outside fuera."""
    return np.where(region_arr, V_inside, V_outside)


def op_clamp(V: np.ndarray, V_min: float = -np.inf, V_max: float = np.inf) -> np.ndarray:
    return np.clip(V, V_min, V_max)


def op_scale(V: np.ndarray, factor: float) -> np.ndarray:
    return V * factor


# ---------------------------------------------------------------------------
# REGISTRY: única fuente de verdad para el composer y los prompts
# ---------------------------------------------------------------------------

@dataclass
class PrimitiveSpec:
    name: str                # nombre exacto que la IA debe usar
    kind: str                # "region" | "profile"
    fn: Callable             # función a llamar
    args: dict               # {nombre: default}
    arg_units: dict          # {nombre: "nm" | "eV" | "" | ...}
    arg_help: dict           # {nombre: descripción corta}
    description: str         # para el prompt de la IA


REGION_PRIMITIVES: dict[str, PrimitiveSpec] = {
    "disk": PrimitiveSpec(
        name="disk", kind="region", fn=region_disk,
        args={"center": [0.0, 0.0], "radius": 10.0},
        arg_units={"center": "nm", "radius": "nm"},
        arg_help={"center": "centro [x,y]", "radius": "radio"},
        description="Disco circular.",
    ),
    "annulus": PrimitiveSpec(
        name="annulus", kind="region", fn=region_annulus,
        args={"center": [0.0, 0.0], "r_inner": 10.0, "r_outer": 20.0},
        arg_units={"center": "nm", "r_inner": "nm", "r_outer": "nm"},
        arg_help={"center":"centro","r_inner":"radio interior","r_outer":"radio exterior"},
        description="Anillo entre dos radios.",
    ),
    "rectangle": PrimitiveSpec(
        name="rectangle", kind="region", fn=region_rectangle,
        args={"center":[0.0,0.0],"Lx":20.0,"Ly":20.0,"angle_deg":0.0},
        arg_units={"center":"nm","Lx":"nm","Ly":"nm","angle_deg":"°"},
        arg_help={"center":"centro","Lx":"ancho x","Ly":"alto y","angle_deg":"rotación"},
        description="Rectángulo centrado, opcionalmente rotado.",
    ),
    "ellipse": PrimitiveSpec(
        name="ellipse", kind="region", fn=region_ellipse,
        args={"center":[0.0,0.0],"a":15.0,"b":10.0,"angle_deg":0.0},
        arg_units={"center":"nm","a":"nm","b":"nm","angle_deg":"°"},
        arg_help={"a":"semieje x","b":"semieje y"},
        description="Elipse estándar (x/a)²+(y/b)²<=1.",
    ),
    "super_ellipse": PrimitiveSpec(
        name="super_ellipse", kind="region", fn=region_super_ellipse,
        args={"center":[0.0,0.0],"a":15.0,"b":15.0,"n":4.0,"angle_deg":0.0},
        arg_units={"center":"nm","a":"nm","b":"nm","n":"","angle_deg":"°"},
        arg_help={"n":"exponente: 2=elipse, 4=cuadrado redondeado, >>2=rectángulo, <2=estrella"},
        description="Super-elipse |x/a|^n+|y/b|^n<=1. Muy útil para puntos cuánticos AFM.",
    ),
    "rose": PrimitiveSpec(
        name="rose", kind="region", fn=region_rose,
        args={"center":[0.0,0.0],"k":4,"R":20.0,"angle_deg":0.0},
        arg_units={"center":"nm","k":"","R":"nm","angle_deg":"°"},
        arg_help={"k":"número de pétalos (par→2k, impar→k)","R":"radio máximo"},
        description="Roseta r<=R·|cos(kθ)|. Para puntos cuánticos con pétalos.",
    ),
    "polygon": PrimitiveSpec(
        name="polygon", kind="region", fn=region_polygon,
        args={"vertices":[[-10.0,-10.0],[10.0,-10.0],[10.0,10.0],[-10.0,10.0]]},
        arg_units={"vertices":"nm"},
        arg_help={"vertices":"lista de [x,y]"},
        description="Polígono arbitrario.",
    ),
    "half_plane": PrimitiveSpec(
        name="half_plane", kind="region", fn=region_half_plane,
        args={"axis":"x","position":0.0,"side":"positive"},
        arg_units={"axis":"","position":"nm","side":""},
        arg_help={"axis":"'x' o 'y'","side":"'positive' o 'negative'"},
        description="Semi-plano respecto a un eje.",
    ),
}


PROFILE_PRIMITIVES: dict[str, PrimitiveSpec] = {
    "constant": PrimitiveSpec(
        name="constant", kind="profile", fn=profile_constant,
        args={"value":0.0},
        arg_units={"value":"eV"},
        arg_help={"value":"valor constante"},
        description="V = value en todas partes. Útil con mask/where.",
    ),
    "gaussian": PrimitiveSpec(
        name="gaussian", kind="profile", fn=profile_gaussian,
        args={"center":[0.0,0.0],"amplitude":-0.3,"sigma":20.0},
        arg_units={"center":"nm","amplitude":"eV","sigma":"nm"},
        arg_help={"amplitude":"negativo→pozo, positivo→barrera","sigma":"ancho"},
        description="Gaussiana 2D. Bloque básico para pozos/barreras suaves.",
    ),
    "mexican_hat": PrimitiveSpec(
        name="mexican_hat", kind="profile", fn=profile_mexican_hat,
        args={"center":[0.0,0.0],"r0":30.0,"depth":0.3},
        arg_units={"center":"nm","r0":"nm","depth":"eV"},
        arg_help={"r0":"radio del mínimo","depth":"profundidad del valle"},
        description="Anillo cuántico (sombrero mexicano).",
    ),
    "harmonic_2d": PrimitiveSpec(
        name="harmonic_2d", kind="profile", fn=profile_harmonic_2d,
        args={"center":[0.0,0.0],"omega_eV":0.0002},
        arg_units={"center":"nm","omega_eV":"eV/nm²"},
        arg_help={"omega_eV":"curvatura ½·ω·r²"},
        description="Parabólico isótropo 2D.",
    ),
    "harmonic_anisotropic": PrimitiveSpec(
        name="harmonic_anisotropic", kind="profile", fn=profile_harmonic_anisotropic,
        args={"center":[0.0,0.0],"omega_x":0.0002,"omega_y":0.0002},
        arg_units={"center":"nm","omega_x":"eV/nm²","omega_y":"eV/nm²"},
        arg_help={},
        description="Parabólico anisótropo (distintas curvaturas en x e y).",
    ),
    "coulomb": PrimitiveSpec(
        name="coulomb", kind="profile", fn=profile_coulomb,
        args={"center":[0.0,0.0],"charge":1.0,"eps_r":12.9,"regularization":1.0},
        arg_units={"center":"nm","charge":"e","eps_r":"","regularization":"nm"},
        arg_help={"charge":"+1 donante, -1 aceptor","eps_r":"constante dieléctrica",
                   "regularization":"radio de corte para evitar singularidad"},
        description="Impureza Coulomb soft. Ry*≈5.5meV en GaAs, a*≈10nm.",
    ),
    "linear": PrimitiveSpec(
        name="linear", kind="profile", fn=profile_linear,
        args={"slope":0.001,"axis":"x","offset":0.0},
        arg_units={"slope":"eV/nm","axis":"","offset":"eV"},
        arg_help={"slope":"pendiente (campo eléctrico)","axis":"'x' o 'y'"},
        description="Término lineal: campo eléctrico uniforme V=F·x.",
    ),
    "polynomial": PrimitiveSpec(
        name="polynomial", kind="profile", fn=profile_polynomial,
        args={"center":[0.0,0.0],"coeffs":[{"i":2,"j":0,"c":0.001}]},
        arg_units={"center":"nm","coeffs":"eV/nm^(i+j)"},
        arg_help={"coeffs":"lista de {i,j,c} → c·xⁱ·yʲ"},
        description="Polinomio bivariado arbitrario.",
    ),
    "exp_decay": PrimitiveSpec(
        name="exp_decay", kind="profile", fn=profile_exp_decay,
        args={"center":[0.0,0.0],"amplitude":-0.3,"length":20.0},
        arg_units={"center":"nm","amplitude":"eV","length":"nm"},
        arg_help={"length":"longitud de decaimiento"},
        description="Decaimiento exponencial radial.",
    ),
    "poschl_teller": PrimitiveSpec(
        name="poschl_teller", kind="profile", fn=profile_pöschl_teller,
        args={"center":[0.0,0.0],"depth":0.3,"alpha":0.05},
        arg_units={"center":"nm","depth":"eV","alpha":"nm⁻¹"},
        arg_help={"alpha":"inverso del ancho"},
        description="Pöschl-Teller radial: -V₀/cosh²(αr).",
    ),
    "raw_expr": PrimitiveSpec(
        name="raw_expr", kind="profile", fn=profile_raw_expr,
        args={"expr":"0.5*0.0002*(x**2+y**2)"},
        arg_units={"expr":""},
        arg_help={"expr":"expresión numpy. Variables: x,y,r,theta. Funciones: sin,cos,exp,sqrt,..."},
        description="Expresión matemática arbitraria. Último recurso para formas exóticas.",
    ),
}


ALL_PRIMITIVES: dict[str, PrimitiveSpec] = {**REGION_PRIMITIVES, **PROFILE_PRIMITIVES}


# ---------------------------------------------------------------------------
# Listados auxiliares
# ---------------------------------------------------------------------------

def list_regions() -> list[str]:
    return list(REGION_PRIMITIVES.keys())


def list_profiles() -> list[str]:
    return list(PROFILE_PRIMITIVES.keys())


def get_spec(name: str) -> PrimitiveSpec:
    if name not in ALL_PRIMITIVES:
        raise KeyError(f"Primitiva desconocida: {name}. "
                       f"Disponibles: {list(ALL_PRIMITIVES)}")
    return ALL_PRIMITIVES[name]
