"""
Biblioteca de primitivas DSL 1D — análoga a primitives.py pero para V(x).

Cada primitiva recibe x (array 1D en nm) y devuelve un array 1D
(boolean si es región, float eV si es perfil).

NO confundir con core/potentials_1d.py — esa es el catálogo legacy.
Esta es la DSL 1D componible para el modo "1D Designer (IA)".
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Callable


# ---------------------------------------------------------------------------
# REGIONES 1D (intervalos)
# ---------------------------------------------------------------------------

def region_1d_interval(x, center=0.0, length=20.0):
    """Intervalo [center - L/2, center + L/2]."""
    return np.abs(x - center) <= length / 2


def region_1d_half_line(x, side="positive", position=0.0):
    """side='positive' → x ≥ position, 'negative' → x ≤ position."""
    return (x >= position) if side == "positive" else (x <= position)


def region_1d_strip(x, x_min=-10.0, x_max=10.0):
    """Intervalo asimétrico [x_min, x_max]."""
    return (x >= x_min) & (x <= x_max)


# ---------------------------------------------------------------------------
# PERFILES DE POTENCIAL 1D (V en eV)
# ---------------------------------------------------------------------------

def profile_1d_constant(x, value=0.0):
    return np.full_like(x, float(value))


def profile_1d_gaussian(x, center=0.0, amplitude=-0.3, sigma=10.0):
    """V = amplitude · exp(-(x-x₀)²/(2σ²)). amp<0 pozo, amp>0 barrera."""
    return amplitude * np.exp(-((x - center) ** 2) / (2 * sigma ** 2))


def profile_1d_harmonic(x, center=0.0, omega_eV=0.0005):
    """V = ½·omega_eV·(x-x₀)². omega_eV en eV/nm²."""
    return 0.5 * omega_eV * (x - center) ** 2


def profile_1d_coulomb(x, center=0.0, charge=1.0, eps_r=12.9, regularization=1.0):
    """
    Coulomb regularizado 1D: V = -e²·k/(εᵣ·√((x-x₀)² + a²))
    k·e ≈ 1.439964 eV·nm. charge=+1 donante.
    """
    r = np.sqrt((x - center) ** 2 + regularization ** 2)
    return -charge * 1.439964 / (eps_r * r)


def profile_1d_linear(x, slope=0.001, offset=0.0):
    """V = slope·x + offset. Campo eléctrico uniforme (Stark)."""
    return slope * x + offset


def profile_1d_polynomial(x, coeffs=None, center=0.0):
    """
    V = Σᵢ c_i · (x-x₀)ⁱ
    coeffs: lista de {i, c}. Ej: [{i:2,c:0.0005}] = oscilador.
    """
    V = np.zeros_like(x)
    if coeffs:
        for term in coeffs:
            V += term["c"] * (x - center) ** term["i"]
    return V


def profile_1d_exp_decay(x, center=0.0, amplitude=-0.3, length=10.0):
    """V = amplitude · exp(-|x-x₀|/length)."""
    return amplitude * np.exp(-np.abs(x - center) / length)


def profile_1d_poschl_teller(x, center=0.0, depth=0.3, alpha=0.1):
    """V = -depth/cosh²(α·(x-x₀)). Analíticamente soluble."""
    return -depth / np.cosh(alpha * (x - center)) ** 2


def profile_1d_morse(x, De=0.3, a=0.1, x0=0.0):
    """V = De·(1 - exp(-a(x-x₀)))² - De. Molécula diatómica."""
    return De * (1 - np.exp(-a * (x - x0))) ** 2 - De


def profile_1d_step(x, position=0.0, height=0.2):
    """V = height para x ≥ position, 0 antes (Heaviside)."""
    V = np.zeros_like(x)
    V[x >= position] = height
    return V


def profile_1d_barrier(x, center=0.0, height=0.3, width=10.0):
    """Barrera rectangular: V = height en |x-c| ≤ w/2, 0 fuera."""
    V = np.zeros_like(x)
    V[np.abs(x - center) <= width / 2] = height
    return V


def profile_1d_infinite_wall(x, position=0.0, side="left", V_inf=1000.0):
    """
    Pared infinita (numéricamente alta).
      side='left'  → V = V_inf para x ≤ position
      side='right' → V = V_inf para x ≥ position
    """
    V = np.zeros_like(x)
    if side == "left":
        V[x <= position] = V_inf
    else:
        V[x >= position] = V_inf
    return V


def profile_1d_triangular(x, slope=0.005, x_wall=-50.0, V_inf=1000.0):
    """V = slope·(x - x_wall) para x > x_wall, infinito para x ≤ x_wall."""
    V = slope * (x - x_wall)
    V[x <= x_wall] = V_inf
    return V


def profile_1d_raw_expr(x, expr=""):
    """Expresión sobre la grilla 1D validada por AST. Variable: x. Constantes: pi, e.
    Funciones: sin, cos, tan, exp, log, sqrt, abs, sinh, cosh, tanh,
               where, heaviside, power, minimum, maximum."""
    from .safe_expr import safe_eval, UnsafeExpressionError
    if not expr:
        return np.zeros_like(x)
    variables = {"x": x, "pi": np.pi, "e": np.e}
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
# Registry 1D
# ---------------------------------------------------------------------------

@dataclass
class PrimitiveSpec1D:
    name: str
    kind: str               # "region" | "profile"
    fn: Callable            # fn(x, **args) -> ndarray
    args: dict
    arg_units: dict
    arg_help: dict
    description: str


REGION_PRIMITIVES_1D: dict[str, PrimitiveSpec1D] = {
    "interval": PrimitiveSpec1D(
        name="interval", kind="region", fn=region_1d_interval,
        args={"center": 0.0, "length": 20.0},
        arg_units={"center":"nm","length":"nm"},
        arg_help={"center":"centro del intervalo","length":"longitud total"},
        description="Intervalo [center-L/2, center+L/2].",
    ),
    "half_line": PrimitiveSpec1D(
        name="half_line", kind="region", fn=region_1d_half_line,
        args={"side":"positive","position":0.0},
        arg_units={"side":"","position":"nm"},
        arg_help={"side":"'positive' (x≥pos) o 'negative' (x≤pos)"},
        description="Semi-recta a un lado de 'position'.",
    ),
    "strip": PrimitiveSpec1D(
        name="strip", kind="region", fn=region_1d_strip,
        args={"x_min":-10.0,"x_max":10.0},
        arg_units={"x_min":"nm","x_max":"nm"},
        arg_help={},
        description="Intervalo asimétrico [x_min, x_max].",
    ),
}


PROFILE_PRIMITIVES_1D: dict[str, PrimitiveSpec1D] = {
    "constant": PrimitiveSpec1D(
        name="constant", kind="profile", fn=profile_1d_constant,
        args={"value":0.0}, arg_units={"value":"eV"}, arg_help={},
        description="V = value constante.",
    ),
    "gaussian": PrimitiveSpec1D(
        name="gaussian", kind="profile", fn=profile_1d_gaussian,
        args={"center":0.0,"amplitude":-0.3,"sigma":10.0},
        arg_units={"center":"nm","amplitude":"eV","sigma":"nm"},
        arg_help={"amplitude":"negativo→pozo, positivo→barrera"},
        description="Gaussiana 1D: pozo o barrera suave.",
    ),
    "harmonic": PrimitiveSpec1D(
        name="harmonic", kind="profile", fn=profile_1d_harmonic,
        args={"center":0.0,"omega_eV":0.0005},
        arg_units={"center":"nm","omega_eV":"eV/nm²"},
        arg_help={"omega_eV":"½·ω·(x-x₀)². Típico: 1e-4 a 1e-3"},
        description="Oscilador armónico 1D — soluble analíticamente.",
    ),
    "coulomb": PrimitiveSpec1D(
        name="coulomb", kind="profile", fn=profile_1d_coulomb,
        args={"center":0.0,"charge":1.0,"eps_r":12.9,"regularization":1.0},
        arg_units={"center":"nm","charge":"e","eps_r":"","regularization":"nm"},
        arg_help={"charge":"+1 donante, -1 aceptor",
                   "regularization":"corte para evitar singularidad"},
        description="Impureza Coulomb 1D regularizada (soft).",
    ),
    "linear": PrimitiveSpec1D(
        name="linear", kind="profile", fn=profile_1d_linear,
        args={"slope":0.001,"offset":0.0},
        arg_units={"slope":"eV/nm","offset":"eV"},
        arg_help={"slope":"campo eléctrico Stark"},
        description="V = slope·x + offset. Campo eléctrico uniforme.",
    ),
    "polynomial": PrimitiveSpec1D(
        name="polynomial", kind="profile", fn=profile_1d_polynomial,
        args={"coeffs":[{"i":2,"c":0.0005}],"center":0.0},
        arg_units={"center":"nm","coeffs":"eV/nmⁱ"},
        arg_help={"coeffs":"lista de {i,c} → c·(x-x₀)ⁱ"},
        description="Polinomio univariado: c₁(x-x₀) + c₂(x-x₀)² + ...",
    ),
    "exp_decay": PrimitiveSpec1D(
        name="exp_decay", kind="profile", fn=profile_1d_exp_decay,
        args={"center":0.0,"amplitude":-0.3,"length":10.0},
        arg_units={"center":"nm","amplitude":"eV","length":"nm"},
        arg_help={"length":"longitud de decaimiento"},
        description="Decaimiento exponencial: V = amp·exp(-|x-x₀|/length).",
    ),
    "poschl_teller": PrimitiveSpec1D(
        name="poschl_teller", kind="profile", fn=profile_1d_poschl_teller,
        args={"center":0.0,"depth":0.3,"alpha":0.1},
        arg_units={"center":"nm","depth":"eV","alpha":"nm⁻¹"},
        arg_help={"alpha":"inverso del ancho del solitón"},
        description="Pöschl-Teller: -V₀/cosh²(α(x-x₀)). Soluble analíticamente.",
    ),
    "morse": PrimitiveSpec1D(
        name="morse", kind="profile", fn=profile_1d_morse,
        args={"De":0.3,"a":0.1,"x0":0.0},
        arg_units={"De":"eV","a":"nm⁻¹","x0":"nm"},
        arg_help={"De":"profundidad disociación","a":"inverso longitud","x0":"equilibrio"},
        description="Potencial de Morse — molécula diatómica anharmónica.",
    ),
    "step": PrimitiveSpec1D(
        name="step", kind="profile", fn=profile_1d_step,
        args={"position":0.0,"height":0.2},
        arg_units={"position":"nm","height":"eV"},
        arg_help={},
        description="Escalón de Heaviside.",
    ),
    "barrier": PrimitiveSpec1D(
        name="barrier", kind="profile", fn=profile_1d_barrier,
        args={"center":0.0,"height":0.3,"width":10.0},
        arg_units={"center":"nm","height":"eV","width":"nm"},
        arg_help={},
        description="Barrera rectangular (tunneling).",
    ),
    "infinite_wall": PrimitiveSpec1D(
        name="infinite_wall", kind="profile", fn=profile_1d_infinite_wall,
        args={"position":0.0,"side":"left","V_inf":1000.0},
        arg_units={"position":"nm","V_inf":"eV"},
        arg_help={"side":"'left' (x≤pos) o 'right' (x≥pos)"},
        description="Pared infinita (V muy alto en un lado).",
    ),
    "triangular": PrimitiveSpec1D(
        name="triangular", kind="profile", fn=profile_1d_triangular,
        args={"slope":0.005,"x_wall":-50.0,"V_inf":1000.0},
        arg_units={"slope":"eV/nm","x_wall":"nm"},
        arg_help={"slope":"campo Stark","x_wall":"posición del muro infinito"},
        description="Triangular (Stark con muro): V=slope·(x-x_wall) + pared a la izq.",
    ),
    "raw_expr": PrimitiveSpec1D(
        name="raw_expr", kind="profile", fn=profile_1d_raw_expr,
        args={"expr":"0.5*0.0005*x**2"},
        arg_units={"expr":""},
        arg_help={"expr":"expresión numpy. Variable: x. Funciones: sin,cos,exp,sqrt,abs,..."},
        description="Expresión matemática arbitraria. Último recurso para formas exóticas.",
    ),
}


ALL_PRIMITIVES_1D: dict[str, PrimitiveSpec1D] = {
    **REGION_PRIMITIVES_1D, **PROFILE_PRIMITIVES_1D
}


def list_regions_1d() -> list[str]:
    return list(REGION_PRIMITIVES_1D.keys())


def list_profiles_1d() -> list[str]:
    return list(PROFILE_PRIMITIVES_1D.keys())


def get_spec_1d(name: str) -> PrimitiveSpec1D:
    if name not in ALL_PRIMITIVES_1D:
        raise KeyError(f"Primitiva 1D '{name}' no existe. "
                        f"Disponibles: {list(ALL_PRIMITIVES_1D)}")
    return ALL_PRIMITIVES_1D[name]
