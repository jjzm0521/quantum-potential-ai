"""
Ejemplo de uso del núcleo científico directamente desde Python/Jupyter.
Útil para el profesor si quiere integrar esto en sus propios scripts.
"""

import sys
sys.path.insert(0, "..")

import numpy as np
import matplotlib.pyplot as plt
from core.solver import solve, make_grid
from core.potentials import evaluate
from core.materials import get_material

# --- Parámetros ---
material = get_material("GaAs")
x_nm, y_nm, X, Y = make_grid(L_nm=200.0, N=96)

# --- Potencial: doble punto cuántico ---
V_eV = evaluate("double_dot", X, Y, {
    "depth": 0.3,
    "sigma": 15.0,
    "separation": 70.0,
})

# --- Solver ---
result = solve(V_eV, x_nm, y_nm, m_eff=material.m_eff, n_states=6)

print("Eigenvalores (meV):")
for i, E in enumerate(result.energies_meV):
    print(f"  E{i} = {E:.3f} meV")

# --- Visualización ---
fig, axes = plt.subplots(1, 3, figsize=(14, 4))

# Potencial
im0 = axes[0].contourf(X, Y, V_eV, levels=50, cmap="RdBu_r")
plt.colorbar(im0, ax=axes[0], label="V (eV)")
axes[0].set_title("Potencial V(x,y)")
axes[0].set_xlabel("x (nm)"); axes[0].set_ylabel("y (nm)")

# Estado base y primer excitado
for i, ax in enumerate(axes[1:], start=0):
    im = ax.contourf(X, Y, result.wavefunctions[i], levels=40, cmap="viridis")
    plt.colorbar(im, ax=ax, label="|ψ|² (nm⁻²)")
    ax.set_title(f"ψ{i}  —  E={result.energies_meV[i]:.2f} meV")
    ax.set_xlabel("x (nm)")

plt.tight_layout()
plt.savefig("resultado_doble_dot.png", dpi=150)
plt.show()
print("Figura guardada en resultado_doble_dot.png")
