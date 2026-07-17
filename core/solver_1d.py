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
from functools import lru_cache

from .solver import HBAR, M_E, EV, NM, lowest_eigsh


@dataclass
class SolverResult1D:
    energies_meV: np.ndarray      # (n_states,)
    wavefunctions: np.ndarray     # (n_states, N)  — ψ_n(x) reales y normalizadas
    prob_density: np.ndarray      # (n_states, N)  — |ψ_n(x)|²
    x_nm: np.ndarray              # grilla x
    V_eV: np.ndarray              # potencial evaluado
    convergence_ok: bool
    n_grid: int
    residuals: np.ndarray
    orthogonality_error: float
    normalization_errors: np.ndarray
    boundary_probabilities: np.ndarray
    backend: str
    requested_states: int
    computed_states: int


@lru_cache(maxsize=8)
def _kinetic_1d_cached(N: int, dx_nm: float, m_eff: float):
    dx = dx_nm * NM
    hbar2_2m = HBAR**2 / (2 * m_eff * M_E)
    return diags(
        [(-hbar2_2m / dx**2) * np.ones(N - 1),
         (2 * hbar2_2m / dx**2) * np.ones(N),
         (-hbar2_2m / dx**2) * np.ones(N - 1)],
        [-1, 0, 1], shape=(N, N), format="csr",
    )


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
    T = _kinetic_1d_cached(N, round(float(dx_nm), 14), round(float(m_eff), 14))

    # Potencial diagonal (Joules)
    V_J = V_eV * EV
    V_op = diags(V_J, 0, format="csr")

    H = T + V_op

    n_req = min(n_states, N - 2)
    eigenvalues, eigenvectors = lowest_eigsh(H, n_req, float(V_J.min()))

    # Ordenar
    idx = np.argsort(eigenvalues)
    eigenvalues  = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    residuals = []
    h_scale = max(float(np.max(np.abs(H.diagonal()))), 1e-30)
    for i in range(n_req):
        vec = eigenvectors[:, i]
        hv = H @ vec
        residuals.append(float(np.linalg.norm(hv - eigenvalues[i] * vec) / h_scale))
    orthogonality_error = float(np.max(np.abs(eigenvectors.conj().T @ eigenvectors - np.eye(n_req))))

    # Normalizar: ∫|ψ|² dx = 1
    wfs = []
    pds = []
    normalization_errors = []
    boundary_probabilities = []
    band = max(1, int(np.ceil(0.05 * N)))
    for i in range(n_req):
        psi = eigenvectors[:, i]
        norm = np.sum(np.abs(psi)**2) * dx_nm
        psi = psi / np.sqrt(norm)
        # Fijar signo: pico positivo
        if abs(psi.min()) > abs(psi.max()):
            psi = -psi
        wfs.append(psi)
        density = np.abs(psi)**2
        pds.append(density)
        normalization_errors.append(float(abs(np.sum(density) * dx_nm - 1.0)))
        boundary_probabilities.append(float((np.sum(density[:band]) + np.sum(density[-band:])) * dx_nm))

    return SolverResult1D(
        energies_meV=eigenvalues / EV * 1000,
        wavefunctions=np.array(wfs),
        prob_density=np.array(pds),
        x_nm=x_nm,
        V_eV=V_eV,
        convergence_ok=bool(np.all(np.isfinite(eigenvalues)) and max(residuals, default=1.0) < 1e-6),
        n_grid=N,
        residuals=np.asarray(residuals),
        orthogonality_error=orthogonality_error,
        normalization_errors=np.asarray(normalization_errors),
        boundary_probabilities=np.asarray(boundary_probabilities),
        backend="scipy-arpack-cpu",
        requested_states=n_req,
        computed_states=n_req,
    )


def make_grid_1d(L_nm: float, N: int = 512) -> np.ndarray:
    return np.linspace(-L_nm / 2, L_nm / 2, N)
