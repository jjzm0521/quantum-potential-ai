"""
Catálogo de potenciales 1D — V(x) en eV, x en nm.

Cada potencial retorna un array 1D de la misma forma que x.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Callable


@dataclass
class PotentialDef1D:
    name: str
    label: str
    description: str
    params: dict
    param_ranges: dict
    param_units: dict
    fn: Callable                        # fn(x, **params) -> ndarray (eV)
    analytic_E: Callable | None = None  # opcional: energías analíticas


# ---------------------------------------------------------------------------
# Potenciales
# ---------------------------------------------------------------------------

def _infinite_well(x, L):
    """Pozo infinito: V=0 en |x|<L/2, muy alto fuera."""
    V = np.zeros_like(x)
    V[np.abs(x) > L / 2] = 1.0e3  # 1000 eV ≈ infinito
    return V


def _finite_well(x, depth, L):
    """Pozo cuadrado de profundidad V0 y ancho L."""
    V = np.zeros_like(x)
    V[np.abs(x) <= L / 2] = -depth
    return V


def _harmonic_1d(x, omega_eV, offset=0.0):
    """Oscilador armónico: V = ½·omega_eV·(x-x0)²."""
    return 0.5 * omega_eV * (x - offset) ** 2


def _double_well(x, depth, separation, sigma):
    """Doble pozo gaussiano (apto para tunneling)."""
    d = separation / 2
    return -depth * (np.exp(-(x - d) ** 2 / (2 * sigma**2)) +
                     np.exp(-(x + d) ** 2 / (2 * sigma**2)))


def _barrier(x, height, width, offset=0.0):
    """Barrera rectangular centrada en offset."""
    V = np.zeros_like(x)
    V[np.abs(x - offset) <= width / 2] = height
    return V


def _step(x, height, offset=0.0):
    """Escalón de Heaviside."""
    V = np.zeros_like(x)
    V[x >= offset] = height
    return V


def _poschl_teller(x, depth, alpha):
    """
    Pöschl-Teller: V = -V0/cosh²(α·x).
    Eigenvalores analíticos: E_n = -(ℏ²α²/2m)·(s-n)²
    donde s(s+1) = 2m·V0/(ℏ²α²).
    """
    return -depth / np.cosh(alpha * x) ** 2


def _morse(x, De, a, x0=0.0):
    """Potencial de Morse: De·(1 - exp(-a(x-x0)))² - De."""
    return De * (1 - np.exp(-a * (x - x0))) ** 2 - De


def _triangular(x, force, x_wall=-50.0):
    """
    Potencial triangular (efecto Stark): V = F·x para x > x_wall,
    infinito a la izquierda del muro.
    """
    V = force * (x - x_wall)
    V[x < x_wall] = 1.0e3
    return V


def _gaussian_well_1d(x, depth, sigma, offset=0.0):
    """Pozo gaussiano suave."""
    return -depth * np.exp(-(x - offset) ** 2 / (2 * sigma**2))


# ---------------------------------------------------------------------------
# Energías analíticas (para validación)
# ---------------------------------------------------------------------------

def _E_infinite_well(L_nm, m_eff, n_max=10):
    """E_n = (n²π²ℏ²)/(2m*L²), n=1,2,..."""
    from .solver import HBAR, M_E, EV, NM
    L = L_nm * NM
    m = m_eff * M_E
    return np.array([
        (n**2 * np.pi**2 * HBAR**2) / (2 * m * L**2) / EV * 1000
        for n in range(1, n_max + 1)
    ])


def _E_harmonic_1d(omega_eV, m_eff, n_max=10):
    """E_n = ℏω(n + ½), n=0,1,2,..."""
    from .solver import HBAR, M_E, EV, NM
    k = omega_eV * EV / NM**2     # J/m²
    m = m_eff * M_E
    omega = np.sqrt(k / m)
    hw_meV = HBAR * omega / EV * 1000
    return np.array([hw_meV * (n + 0.5) for n in range(n_max)])


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

POTENTIALS_1D: dict[str, PotentialDef1D] = {
    "infinite_well": PotentialDef1D(
        name="infinite_well",
        label="Pozo Infinito",
        description="Caja cuántica 1D ideal — el ejemplo clásico de mecánica cuántica",
        params={"L": 40.0},
        param_ranges={"L": (5.0, 200.0, 1.0)},
        param_units={"L": "nm"},
        fn=_infinite_well,
        analytic_E=lambda p, m_eff: _E_infinite_well(p["L"], m_eff),
    ),
    "finite_well": PotentialDef1D(
        name="finite_well",
        label="Pozo Finito",
        description="Pozo cuadrado de profundidad y ancho ajustables",
        params={"depth": 0.3, "L": 30.0},
        param_ranges={"depth": (0.01, 2.0, 0.01),
                      "L": (5.0, 150.0, 1.0)},
        param_units={"depth": "eV", "L": "nm"},
        fn=_finite_well,
    ),
    "harmonic": PotentialDef1D(
        name="harmonic",
        label="Oscilador Armónico",
        description="V = ½·k·x² — soluble analíticamente, base de muchos sistemas",
        params={"omega_eV": 0.0005, "offset": 0.0},
        param_ranges={"omega_eV": (0.00001, 0.005, 0.00001),
                      "offset": (-50.0, 50.0, 1.0)},
        param_units={"omega_eV": "eV/nm²", "offset": "nm"},
        fn=_harmonic_1d,
        analytic_E=lambda p, m_eff: _E_harmonic_1d(p["omega_eV"], m_eff),
    ),
    "double_well": PotentialDef1D(
        name="double_well",
        label="Doble Pozo",
        description="Dos pozos gaussianos acoplados — splitting por tunneling",
        params={"depth": 0.3, "separation": 30.0, "sigma": 8.0},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "separation": (5.0, 120.0, 1.0),
                      "sigma": (2.0, 30.0, 0.5)},
        param_units={"depth": "eV", "separation": "nm", "sigma": "nm"},
        fn=_double_well,
    ),
    "barrier": PotentialDef1D(
        name="barrier",
        label="Barrera Rectangular",
        description="Barrera de altura V₀ y ancho L — tunneling cuántico",
        params={"height": 0.3, "width": 10.0, "offset": 0.0},
        param_ranges={"height": (0.01, 2.0, 0.01),
                      "width": (1.0, 60.0, 0.5),
                      "offset": (-50.0, 50.0, 1.0)},
        param_units={"height": "eV", "width": "nm", "offset": "nm"},
        fn=_barrier,
    ),
    "step": PotentialDef1D(
        name="step",
        label="Escalón",
        description="Potencial de Heaviside — reflexión y transmisión cuántica",
        params={"height": 0.2, "offset": 0.0},
        param_ranges={"height": (-1.0, 1.0, 0.01),
                      "offset": (-50.0, 50.0, 1.0)},
        param_units={"height": "eV", "offset": "nm"},
        fn=_step,
    ),
    "poschl_teller": PotentialDef1D(
        name="poschl_teller",
        label="Pöschl-Teller",
        description="V = -V₀/cosh²(αx) — solitón, soluble analíticamente",
        params={"depth": 0.2, "alpha": 0.05},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "alpha": (0.01, 0.5, 0.005)},
        param_units={"depth": "eV", "alpha": "nm⁻¹"},
        fn=_poschl_teller,
    ),
    "morse": PotentialDef1D(
        name="morse",
        label="Morse (molecular)",
        description="V = D·(1-e^(-a(x-x₀)))²-D — molécula diatómica, anharmónico",
        params={"De": 0.5, "a": 0.1, "x0": 0.0},
        param_ranges={"De": (0.01, 2.0, 0.01),
                      "a": (0.01, 1.0, 0.005),
                      "x0": (-30.0, 30.0, 1.0)},
        param_units={"De": "eV", "a": "nm⁻¹", "x0": "nm"},
        fn=_morse,
    ),
    "triangular": PotentialDef1D(
        name="triangular",
        label="Triangular (Stark)",
        description="V = F·x con muro — campo eléctrico uniforme",
        params={"force": 0.005, "x_wall": -50.0},
        param_ranges={"force": (0.0001, 0.05, 0.0001),
                      "x_wall": (-100.0, 0.0, 1.0)},
        param_units={"force": "eV/nm", "x_wall": "nm"},
        fn=_triangular,
    ),
    "gaussian_well": PotentialDef1D(
        name="gaussian_well",
        label="Pozo Gaussiano",
        description="Pozo suave V = -V₀·exp(-x²/2σ²)",
        params={"depth": 0.3, "sigma": 15.0, "offset": 0.0},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "sigma": (3.0, 80.0, 0.5),
                      "offset": (-50.0, 50.0, 1.0)},
        param_units={"depth": "eV", "sigma": "nm", "offset": "nm"},
        fn=_gaussian_well_1d,
    ),
}


def evaluate_1d(pot_name: str, x: np.ndarray, params: dict) -> np.ndarray:
    return POTENTIALS_1D[pot_name].fn(x, **params)


def list_potentials_1d() -> list[str]:
    return list(POTENTIALS_1D.keys())
