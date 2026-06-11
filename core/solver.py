"""
Solver Schrödinger 2D estacionario — método de diferencias finitas.

Ecuación: [-ℏ²/2m* ∇² + V(x,y)] ψ = E ψ

Unidades de entrada:
  - V en eV
  - coordenadas en nm
  - m_eff en unidades de masa electrón (m_e)

Unidades de salida:
  - eigenvalores E en meV
  - eigenvectores normalizados |ψ|² (nm⁻²)
"""

from __future__ import annotations
import numpy as np
from scipy.sparse import diags, kron, eye
from scipy.sparse.linalg import eigsh
from dataclasses import dataclass

# Constantes
HBAR  = 1.054571817e-34   # J·s
M_E   = 9.10938e-31        # kg
EV    = 1.60218e-19        # J/eV
NM    = 1e-9               # m/nm


@dataclass
class SolverResult:
    energies_meV: np.ndarray      # shape (n_states,)
    wavefunctions: np.ndarray     # shape (n_states, Ny, Nx)  — |ψ|² norm 1
    x_nm: np.ndarray              # grilla x
    y_nm: np.ndarray              # grilla y
    V_eV: np.ndarray              # potencial evaluado
    convergence_ok: bool
    grid_size: tuple[int, int]


def solve(
    V_eV: np.ndarray,
    x_nm: np.ndarray,
    y_nm: np.ndarray,
    m_eff: float,
    n_states: int = 8,
) -> SolverResult:
    """
    V_eV  : array 2D shape (Ny, Nx) en eV
    x_nm  : array 1D en nm (equiespaciado)
    y_nm  : array 1D en nm (equiespaciado)
    m_eff : masa efectiva en unidades de m_e
    """
    Ny, Nx = V_eV.shape
    dx_nm = x_nm[1] - x_nm[0]
    dy_nm = y_nm[1] - y_nm[0]

    # Convertir a SI
    dx = dx_nm * NM
    dy = dy_nm * NM
    m  = m_eff * M_E

    # Prefactor cinético en Joules: ℏ²/(2m)
    hbar2_2m = HBAR**2 / (2 * m)

    # Operador cinético 1D (diferencias finitas centradas)
    def kinetic_1d(N, dq):
        diag_main = -2 * np.ones(N)
        diag_off  = np.ones(N - 1)
        T = diags([diag_off, diag_main, diag_off], [-1, 0, 1],
                  shape=(N, N), format="csr")
        return (-hbar2_2m / dq**2) * T   # en Joules

    Tx = kinetic_1d(Nx, dx)
    Ty = kinetic_1d(Ny, dy)
    Ix = eye(Nx, format="csr")
    Iy = eye(Ny, format="csr")

    # Hamiltoniano cinético 2D: T = Ty⊗Ix + Iy⊗Tx
    H_kin = kron(Ty, Ix, format="csr") + kron(Iy, Tx, format="csr")

    # Potencial como diagonal (Joules)
    V_flat = V_eV.flatten() * EV
    H_pot  = diags(V_flat, 0, format="csr")

    H = H_kin + H_pot

    # Resolver n_states eigenvalores más bajos
    n_req = min(n_states, Nx * Ny - 2)
    eigenvalues, eigenvectors = eigsh(H, k=n_req, which="SA")

    # Ordenar por energía
    idx = np.argsort(eigenvalues)
    eigenvalues  = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Normalizar |ψ|² sobre la grilla (integral ≈ 1)
    dA = dx_nm * dy_nm  # nm²
    wavefunctions = []
    for i in range(n_req):
        psi = eigenvectors[:, i].reshape(Ny, Nx)
        norm = np.sum(np.abs(psi)**2) * dA
        psi /= np.sqrt(norm)
        wavefunctions.append(np.abs(psi)**2)

    energies_meV = eigenvalues / EV * 1000   # J → eV → meV

    # Chequeo básico de convergencia: todos los eigenvalores deben ser reales
    convergence_ok = bool(np.all(np.isfinite(energies_meV)))

    return SolverResult(
        energies_meV=energies_meV,
        wavefunctions=np.array(wavefunctions),
        x_nm=x_nm,
        y_nm=y_nm,
        V_eV=V_eV,
        convergence_ok=convergence_ok,
        grid_size=(Ny, Nx),
    )


def make_grid(L_nm: float, N: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Genera grilla cuadrada [-L/2, L/2]² de N×N puntos.
    Retorna (x, y, X_mesh, Y_mesh).
    """
    x = np.linspace(-L_nm / 2, L_nm / 2, N)
    y = np.linspace(-L_nm / 2, L_nm / 2, N)
    X, Y = np.meshgrid(x, y)
    return x, y, X, Y


def recommend_grid(sigma_nm: float) -> tuple[float, int]:
    """Sugiere dominio L y resolución N según la escala del potencial."""
    L = max(6 * sigma_nm, 100.0)
    N = min(max(int(L / sigma_nm * 8), 64), 256)
    return L, N
