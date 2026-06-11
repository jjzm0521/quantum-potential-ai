"""
Solver Schrödinger 1D estacionario — diferencias finitas tridiagonales.

Ecuación: [-ℏ²/2m* d²/dx² + V(x)] ψ(x) = E ψ(x)

Unidades:
  - V en eV
  - x en nm
  - m_eff en m_e
  - E_out en meV
"""

from __future__ import annotations
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import eigsh
from dataclasses import dataclass

from .solver import HBAR, M_E, EV, NM


@dataclass
class SolverResult1D:
    energies_meV: np.ndarray      # (n_states,)
    wavefunctions: np.ndarray     # (n_states, N)  — ψ_n(x) reales y normalizadas
    prob_density: np.ndarray      # (n_states, N)  — |ψ_n(x)|²
    x_nm: np.ndarray              # grilla x
    V_eV: np.ndarray              # potencial evaluado
    convergence_ok: bool
    n_grid: int


def solve_1d(
    V_eV: np.ndarray,
    x_nm: np.ndarray,
    m_eff: float,
    n_states: int = 6,
) -> SolverResult1D:
    """
    V_eV : array 1D shape (N,) en eV
    x_nm : array 1D en nm (equiespaciado)
    """
    N = len(x_nm)
    dx_nm = x_nm[1] - x_nm[0]
    dx = dx_nm * NM
    m = m_eff * M_E

    hbar2_2m = HBAR**2 / (2 * m)

    # Operador cinético tridiagonal en Joules
    diag_main = (2 * hbar2_2m / dx**2) * np.ones(N)
    diag_off  = (-hbar2_2m / dx**2) * np.ones(N - 1)
    T = diags([diag_off, diag_main, diag_off], [-1, 0, 1],
              shape=(N, N), format="csr")

    # Potencial diagonal (Joules)
    V_J = V_eV * EV
    V_op = diags(V_J, 0, format="csr")

    H = T + V_op

    n_req = min(n_states, N - 2)
    eigenvalues, eigenvectors = eigsh(H, k=n_req, which="SA")

    # Ordenar
    idx = np.argsort(eigenvalues)
    eigenvalues  = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Normalizar: ∫|ψ|² dx = 1
    wfs = []
    pds = []
    for i in range(n_req):
        psi = eigenvectors[:, i]
        norm = np.sum(np.abs(psi)**2) * dx_nm
        psi = psi / np.sqrt(norm)
        # Fijar signo: pico positivo
        if abs(psi.min()) > abs(psi.max()):
            psi = -psi
        wfs.append(psi)
        pds.append(np.abs(psi)**2)

    return SolverResult1D(
        energies_meV=eigenvalues / EV * 1000,
        wavefunctions=np.array(wfs),
        prob_density=np.array(pds),
        x_nm=x_nm,
        V_eV=V_eV,
        convergence_ok=bool(np.all(np.isfinite(eigenvalues))),
        n_grid=N,
    )


def make_grid_1d(L_nm: float, N: int = 512) -> np.ndarray:
    return np.linspace(-L_nm / 2, L_nm / 2, N)
