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
from functools import lru_cache

# Constantes
HBAR  = 1.054571817e-34   # J·s
M_E   = 9.10938e-31        # kg
EV    = 1.60218e-19        # J/eV
NM    = 1e-9               # m/nm


def lowest_eigsh(H, k: int, v_min_J: float):
    """Eigenvalores más bajos de H, robusto ante espectros muy anchos.

    Potenciales con paredes repulsivas (Morse, triangular, r^4) tienen V_max
    enorme y `eigsh(which="SA")` puede no converger (ARPACK -1). El modo
    shift-invert (sigma cerca del fondo del pozo) converge rápido en esos casos;
    lo usamos como fallback para no pagar la factorización LU cuando no hace falta.
    """
    from scipy.sparse.linalg import ArpackNoConvergence
    n = H.shape[0]
    # A wider Krylov subspace is important for symmetric 2D potentials: with
    # ARPACK's small default subspace, one member of a degenerate pair can be
    # replaced by a higher state at the requested boundary.  A fixed starting
    # vector also makes repeated verification runs reproducible.
    ncv = min(n - 1, max(4 * k + 1, 32))
    indices = np.arange(1, n + 1, dtype=float)
    v0 = np.sin(indices * 0.754877666) + np.cos(indices * 0.569840291)
    try:
        return eigsh(H, k=k, which="SA", ncv=ncv, v0=v0)
    except ArpackNoConvergence:
        sigma = v_min_J - abs(v_min_J) * 1e-3 - 1e-25
        return eigsh(H, k=k, sigma=sigma, which="LM", ncv=ncv, v0=v0)


def _work_state_count(requested: int, dimension: int) -> int:
    """Compute extra Ritz pairs so a degeneracy at the request boundary is not missed."""
    requested = min(max(1, int(requested)), dimension - 2)
    # ARPACK starts from a single vector.  On highly symmetric grids that
    # vector can have almost no projection on one symmetry sector, so a small
    # oversampling still misses one member of a degenerate pair.  Eight spare
    # Ritz pairs proved sufficient for the disk/ring regression matrix while
    # remaining tiny compared with the N² Hamiltonian.
    extra = max(8, requested)
    return min(requested + extra, dimension - 2)


@lru_cache(maxsize=4)
def _kinetic_2d_cached(
    Nx: int,
    Ny: int,
    dx_nm: float,
    dy_nm: float,
    m_eff: float,
):
    """Reusable sparse kinetic operator; sweeps only rebuild the potential diagonal."""
    dx = dx_nm * NM
    dy = dy_nm * NM
    hbar2_2m = HBAR**2 / (2 * m_eff * M_E)

    def kinetic_1d(size, spacing):
        return (-hbar2_2m / spacing**2) * diags(
            [np.ones(size - 1), -2 * np.ones(size), np.ones(size - 1)],
            [-1, 0, 1], shape=(size, size), format="csr",
        )

    Tx = kinetic_1d(Nx, dx)
    Ty = kinetic_1d(Ny, dy)
    return (
        kron(Ty, eye(Nx, format="csr"), format="csr")
        + kron(eye(Ny, format="csr"), Tx, format="csr")
    )


@dataclass
class SolverResult:
    energies_meV: np.ndarray      # shape (n_states,)
    wavefunctions: np.ndarray     # shape (n_states, Ny, Nx)  — |ψ|² norm 1
    x_nm: np.ndarray              # grilla x
    y_nm: np.ndarray              # grilla y
    V_eV: np.ndarray              # potencial evaluado
    convergence_ok: bool
    grid_size: tuple[int, int]
    residuals: np.ndarray
    orthogonality_error: float
    normalization_errors: np.ndarray
    boundary_probabilities: np.ndarray
    backend: str
    requested_states: int
    computed_states: int


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

    H_kin = _kinetic_2d_cached(
        Nx, Ny, round(float(dx_nm), 14), round(float(dy_nm), 14), round(float(m_eff), 14)
    )

    # Potencial como diagonal (Joules)
    V_flat = V_eV.flatten() * EV
    H_pot  = diags(V_flat, 0, format="csr")

    H = H_kin + H_pot

    # Resolver n_states eigenvalores más bajos
    n_req = min(n_states, Nx * Ny - 2)
    n_work = _work_state_count(n_req, Nx * Ny)
    eigenvalues, eigenvectors = lowest_eigsh(H, n_work, float(V_flat.min()))

    # Ordenar por energía
    idx = np.argsort(eigenvalues)
    eigenvalues  = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    eigenvalues = eigenvalues[:n_req]
    eigenvectors = eigenvectors[:, :n_req]

    residuals = []
    h_scale = max(float(np.max(np.abs(H.diagonal()))), 1e-30)
    for i in range(n_req):
        vec = eigenvectors[:, i]
        hv = H @ vec
        residuals.append(float(np.linalg.norm(hv - eigenvalues[i] * vec) / h_scale))
    gram = eigenvectors.conj().T @ eigenvectors
    orthogonality_error = float(np.max(np.abs(gram - np.eye(n_req))))

    # Normalizar |ψ|² sobre la grilla (integral ≈ 1)
    dA = dx_nm * dy_nm  # nm²
    wavefunctions = []
    normalization_errors = []
    boundary_probabilities = []
    band = max(1, int(np.ceil(0.05 * min(Nx, Ny))))
    for i in range(n_req):
        psi = eigenvectors[:, i].reshape(Ny, Nx)
        norm = np.sum(np.abs(psi)**2) * dA
        psi /= np.sqrt(norm)
        density = np.abs(psi)**2
        normalization_errors.append(float(abs(np.sum(density) * dA - 1.0)))
        boundary = np.zeros((Ny, Nx), dtype=bool)
        boundary[:band, :] = True
        boundary[-band:, :] = True
        boundary[:, :band] = True
        boundary[:, -band:] = True
        boundary_probabilities.append(float(np.sum(density[boundary]) * dA))
        wavefunctions.append(density)

    energies_meV = eigenvalues / EV * 1000   # J → eV → meV

    # Chequeo básico de convergencia: todos los eigenvalores deben ser reales
    convergence_ok = bool(np.all(np.isfinite(energies_meV)) and max(residuals, default=1.0) < 1e-6)

    return SolverResult(
        energies_meV=energies_meV,
        wavefunctions=np.array(wavefunctions),
        x_nm=x_nm,
        y_nm=y_nm,
        V_eV=V_eV,
        convergence_ok=convergence_ok,
        grid_size=(Ny, Nx),
        residuals=np.asarray(residuals),
        orthogonality_error=orthogonality_error,
        normalization_errors=np.asarray(normalization_errors),
        boundary_probabilities=np.asarray(boundary_probabilities),
        backend="scipy-arpack-cpu",
        requested_states=n_req,
        computed_states=n_work,
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
