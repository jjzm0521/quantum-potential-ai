"""
Catálogo de potenciales V(x,y) en eV.
Coordenadas x, y en nanómetros.
Cada potencial devuelve un array 2D shape (Ny, Nx).
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Tipo base
# ---------------------------------------------------------------------------

@dataclass
class PotentialDef:
    name: str
    label: str
    description: str
    params: dict            # {nombre: valor_defecto}
    param_ranges: dict      # {nombre: (min, max, step)}
    param_units: dict       # {nombre: "eV" / "nm" / ""}
    fn: Callable            # fn(X, Y, **params) -> ndarray en eV


# ---------------------------------------------------------------------------
# Funciones de potencial
# ---------------------------------------------------------------------------

def _quantum_dot(X, Y, depth, sigma, offset_x=0.0, offset_y=0.0):
    r2 = (X - offset_x)**2 + (Y - offset_y)**2
    return -depth * np.exp(-r2 / (2 * sigma**2))


def _quantum_ring(X, Y, depth, r0, width):
    r = np.sqrt(X**2 + Y**2)
    return depth * (r**2 - r0**2)**2 / (r0**4) - depth


def _double_dot(X, Y, depth, sigma, separation):
    d = separation / 2
    r2_L = (X + d)**2 + Y**2
    r2_R = (X - d)**2 + Y**2
    return -depth * (np.exp(-r2_L / (2 * sigma**2)) +
                     np.exp(-r2_R / (2 * sigma**2)))


def _harmonic(X, Y, omega_eV, offset_x=0.0, offset_y=0.0):
    r2 = (X - offset_x)**2 + (Y - offset_y)**2
    return 0.5 * omega_eV * r2


def _rectangular_well(X, Y, depth, Lx, Ly):
    V = np.zeros_like(X)
    mask = (np.abs(X) > Lx / 2) | (np.abs(Y) > Ly / 2)
    V[mask] = 0.0
    V[~mask] = -depth
    return V


def _saddle_point(X, Y, height, curvx, curvy):
    return height * (-curvx * X**2 + curvy * Y**2)


def _triple_dot(X, Y, depth, sigma, r_triangle):
    angles = [0, 2*np.pi/3, 4*np.pi/3]
    V = np.zeros_like(X)
    for a in angles:
        cx = r_triangle * np.cos(a)
        cy = r_triangle * np.sin(a)
        V += -depth * np.exp(-((X-cx)**2 + (Y-cy)**2) / (2*sigma**2))
    return V


def _gaussian_sum(X, Y, centers, depths, sigmas):
    """Suma arbitraria de Gaussianas. centers: list of (x,y) en nm."""
    V = np.zeros_like(X)
    for (cx, cy), d, s in zip(centers, depths, sigmas):
        V += -d * np.exp(-((X-cx)**2 + (Y-cy)**2) / (2*s**2))
    return V


# ---------------------------------------------------------------------------
# Catálogo exportado
# ---------------------------------------------------------------------------

POTENTIALS: dict[str, PotentialDef] = {
    "quantum_dot": PotentialDef(
        name="quantum_dot",
        label="Punto Cuántico",
        description="Pozo gaussiano circular — modelo estándar de quantum dot",
        params={"depth": 0.3, "sigma": 20.0, "offset_x": 0.0, "offset_y": 0.0},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "sigma": (5.0, 100.0, 1.0),
                      "offset_x": (-50.0, 50.0, 1.0),
                      "offset_y": (-50.0, 50.0, 1.0)},
        param_units={"depth": "eV", "sigma": "nm",
                     "offset_x": "nm", "offset_y": "nm"},
        fn=_quantum_dot,
    ),
    "quantum_ring": PotentialDef(
        name="quantum_ring",
        label="Anillo Cuántico",
        description="Potencial sombrero mexicano — anillo de confinamiento",
        params={"depth": 0.3, "r0": 30.0, "width": 10.0},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "r0": (5.0, 80.0, 1.0),
                      "width": (3.0, 40.0, 1.0)},
        param_units={"depth": "eV", "r0": "nm", "width": "nm"},
        fn=_quantum_ring,
    ),
    "double_dot": PotentialDef(
        name="double_dot",
        label="Doble Punto Cuántico",
        description="Dos pozos gaussianos acoplados — para estudiar tunneling",
        params={"depth": 0.3, "sigma": 15.0, "separation": 60.0},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "sigma": (5.0, 50.0, 1.0),
                      "separation": (10.0, 150.0, 2.0)},
        param_units={"depth": "eV", "sigma": "nm", "separation": "nm"},
        fn=_double_dot,
    ),
    "harmonic": PotentialDef(
        name="harmonic",
        label="Oscilador Armónico 2D",
        description="Potencial parabólico — exactamente soluble, ideal para validación",
        params={"omega_eV": 0.0002, "offset_x": 0.0, "offset_y": 0.0},
        param_ranges={"omega_eV": (0.00001, 0.001, 0.00001),
                      "offset_x": (-50.0, 50.0, 1.0),
                      "offset_y": (-50.0, 50.0, 1.0)},
        param_units={"omega_eV": "eV/nm²", "offset_x": "nm", "offset_y": "nm"},
        fn=_harmonic,
    ),
    "rectangular_well": PotentialDef(
        name="rectangular_well",
        label="Pozo Rectangular",
        description="Caja cuántica rectangular — modelo elemental",
        params={"depth": 0.5, "Lx": 60.0, "Ly": 60.0},
        param_ranges={"depth": (0.01, 2.0, 0.01),
                      "Lx": (10.0, 150.0, 2.0),
                      "Ly": (10.0, 150.0, 2.0)},
        param_units={"depth": "eV", "Lx": "nm", "Ly": "nm"},
        fn=_rectangular_well,
    ),
    "saddle_point": PotentialDef(
        name="saddle_point",
        label="Punto de Silla",
        description="Barrera de silla — relevante en junctions y quantum point contacts",
        params={"height": 0.2, "curvx": 0.0001, "curvy": 0.0001},
        param_ranges={"height": (0.01, 1.0, 0.01),
                      "curvx": (0.000001, 0.001, 0.000001),
                      "curvy": (0.000001, 0.001, 0.000001)},
        param_units={"height": "eV", "curvx": "eV/nm²", "curvy": "eV/nm²"},
        fn=_saddle_point,
    ),
    "triple_dot": PotentialDef(
        name="triple_dot",
        label="Triple Punto Cuántico",
        description="Tres puntos en triángulo equilátero — geometría de spin qubit",
        params={"depth": 0.3, "sigma": 12.0, "r_triangle": 40.0},
        param_ranges={"depth": (0.01, 1.0, 0.01),
                      "sigma": (5.0, 40.0, 1.0),
                      "r_triangle": (10.0, 80.0, 1.0)},
        param_units={"depth": "eV", "sigma": "nm", "r_triangle": "nm"},
        fn=_triple_dot,
    ),
}


def evaluate(pot_name: str, X: np.ndarray, Y: np.ndarray, params: dict) -> np.ndarray:
    """Evalúa potencial en la grilla (X, Y) con parámetros dados."""
    pdef = POTENTIALS[pot_name]
    return pdef.fn(X, Y, **params)


def list_potentials() -> list[str]:
    return list(POTENTIALS.keys())
