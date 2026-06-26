"""
qpot.render — render de potenciales y funciones de onda a PNG con matplotlib.

Usamos matplotlib (backend Agg) en vez de plotly porque produce PNG directos sin
dependencias extra (kaleido). El agente externo LEE estos PNG para "ver" el potencial:
es la pieza que cierra el loop visual sin gastar API.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def _clip_range(V_meV: np.ndarray) -> tuple[float | None, float | None]:
    """Rango de visualización que ENFOCA el pozo.

    En anillos/barreras el potencial crece como r^4 hacia los bordes y aplasta el
    pozo. Si hay mínimo negativo (pozo), limitamos el techo a ~media profundidad por
    encima de cero; si no, usamos percentiles robustos.
    """
    finite = V_meV[np.isfinite(V_meV)]
    if finite.size == 0:
        return None, None
    vmin, vmax = float(finite.min()), float(finite.max())
    if vmin < -1e-6:  # hay pozo
        hi = min(vmax, abs(vmin) * 0.5)
        if hi <= vmin:
            hi = vmin + abs(vmin) * 0.5 + 1.0
        return vmin, hi
    if vmin >= 0:
        return vmin, vmax
    return float(np.percentile(finite, 1)), float(np.percentile(finite, 90))


def render_potential(field: dict, out_path: str | Path, title: str = "Potencial V") -> Path:
    """Dibuja V(x) (1D) o V(x,y) (2D) a partir de la salida de session.evaluate_potential."""
    out = Path(out_path)
    if field["dim"] == 1:
        _render_potential_1d(field, out, title)
    else:
        _render_potential_2d(field, out, title)
    return out


def _render_potential_1d(field: dict, out: Path, title: str) -> None:
    x = field["x_nm"]
    V = field["V_eV"] * 1000.0  # meV para legibilidad
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=110)
    # Clip de paredes infinitas para que la escala sea útil.
    finite = V[np.isfinite(V)]
    if finite.size:
        hi = np.percentile(finite, 99)
        lo = np.percentile(finite, 1)
        pad = max(10.0, 0.1 * (hi - lo))
        ax.set_ylim(lo - pad, hi + pad)
    ax.plot(x, V, color="#1f3b73", lw=2)
    ax.axhline(0, color="#999", lw=0.8, ls="--")
    ax.set_xlabel("x (nm)")
    ax.set_ylabel("V (meV)")
    ax.set_title(title)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def _render_potential_2d(field: dict, out: Path, title: str) -> None:
    """Dos paneles: superficie 3D (lo que se pidió para los pozos 2D) + vista superior."""
    x = field["x_nm"]
    y = field["y_nm"]
    V = field["V_eV"] * 1000.0  # meV
    X, Y = np.meshgrid(x, y)

    # Recorta el rango enfocando el pozo (ver _clip_range).
    zmin, zmax = _clip_range(V)
    Vc = np.clip(V, zmin, zmax) if zmin is not None else V

    fig = plt.figure(figsize=(10.2, 4.6), dpi=110)

    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    surf = ax1.plot_surface(X, Y, Vc, cmap="viridis", vmin=zmin, vmax=zmax,
                            linewidth=0, antialiased=True, rcount=100, ccount=100)
    ax1.set_xlabel("x (nm)")
    ax1.set_ylabel("y (nm)")
    ax1.set_zlabel("V (meV)")
    ax1.set_title("Superficie 3D")
    ax1.view_init(elev=38, azim=-55)
    fig.colorbar(surf, ax=ax1, shrink=0.55, pad=0.08, label="V (meV)")

    ax2 = fig.add_subplot(1, 2, 2)
    im = ax2.pcolormesh(x, y, V, shading="auto", cmap="viridis", vmin=zmin, vmax=zmax)
    fig.colorbar(im, ax=ax2, label="V (meV, escala recortada)")
    ax2.set_xlabel("x (nm)")
    ax2.set_ylabel("y (nm)")
    ax2.set_title("Vista superior")
    ax2.set_aspect("equal")

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def render_wavefunctions(result, dim: int, out_path: str | Path, n_show: int = 4) -> Path:
    """Dibuja los primeros estados. 1D: estilo libro de texto. 2D: grid de |ψ|²."""
    out = Path(out_path)
    if dim == 1:
        _render_wavefunctions_1d(result, out, n_show)
    else:
        _render_wavefunctions_2d(result, out, n_show)
    return out


def _render_wavefunctions_1d(result, out: Path, n_show: int) -> None:
    x = result.x_nm
    V = result.V_eV * 1000.0  # meV
    E = result.energies_meV
    n = min(n_show, len(E))

    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=110)
    finite = V[np.isfinite(V)]
    if finite.size:
        hi = np.percentile(finite, 99)
        lo = min(np.percentile(finite, 1), float(np.min(E)) - 10 if n else 0.0)
        ax.set_ylim(lo - 15, hi + 15)
    ax.plot(x, V, color="#333", lw=1.8, label="V(x)")

    # Escala de psi para que se vea sobre el nivel de energía.
    spacing = (float(np.max(E[:n])) - float(np.min(E[:n]))) / max(1, n) if n > 1 else 40.0
    amp = max(15.0, abs(spacing))
    for i in range(n):
        psi = result.wavefunctions[i]
        psi_scaled = psi / (np.max(np.abs(psi)) + 1e-12) * amp + E[i]
        ax.axhline(E[i], color="#bbb", lw=0.6, ls=":")
        ax.plot(x, psi_scaled, lw=1.6, label=f"E{i}={E[i]:.1f} meV")
    ax.set_xlabel("x (nm)")
    ax.set_ylabel("Energía (meV) / ψ desplazada")
    ax.set_title("Estados ligados (1D)")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def _render_wavefunctions_2d(result, out: Path, n_show: int) -> None:
    x = result.x_nm
    y = result.y_nm
    E = result.energies_meV
    n = min(n_show, len(E))
    cols = min(2, n) if n else 1
    rows = int(np.ceil(n / cols)) if n else 1

    fig, axes = plt.subplots(rows, cols, figsize=(4.4 * cols, 3.6 * rows), dpi=110,
                             squeeze=False)
    for idx in range(rows * cols):
        ax = axes[idx // cols][idx % cols]
        if idx < n:
            dens = result.wavefunctions[idx]  # |ψ|² (2D ya viene como densidad)
            ax.pcolormesh(x, y, dens, shading="auto", cmap="magma")
            ax.set_title(f"|ψ|²  E{idx}={E[idx]:.1f} meV", fontsize=9)
            ax.set_aspect("equal")
            ax.set_xlabel("x (nm)", fontsize=8)
            ax.set_ylabel("y (nm)", fontsize=8)
        else:
            ax.axis("off")
    fig.suptitle("Densidades de probabilidad (2D)")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


# ---------------------------------------------------------------------------
# HTML 3D interactivo (plotly, opcional) — sin servidor, se abre en el navegador
# ---------------------------------------------------------------------------

def render_potential_html(field: dict, out_path: str | Path) -> Path:
    """Escribe un HTML autocontenido con el potencial interactivo (rotar/zoom en 3D
    para 2D). Requiere plotly; no necesita Streamlit ni servidor."""
    try:
        import plotly.graph_objects as go
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Para --html necesitas plotly:  pip install plotly") from exc

    out = Path(out_path)
    if field["dim"] == 1:
        V = field["V_eV"] * 1000.0
        fig = go.Figure(go.Scatter(x=field["x_nm"], y=V, mode="lines",
                                   line=dict(color="#1f3b73", width=2)))
        fig.update_layout(title="Potencial V(x)", xaxis_title="x (nm)",
                          yaxis_title="V (meV)", template="plotly_white")
    else:
        x, y = field["x_nm"], field["y_nm"]
        V = field["V_eV"] * 1000.0
        cmin, cmax = _clip_range(V)
        Vc = np.clip(V, cmin, cmax) if cmin is not None else V
        fig = go.Figure(go.Surface(x=x, y=y, z=Vc, colorscale="Viridis",
                                   cmin=cmin, cmax=cmax,
                                   colorbar=dict(title="V (meV)")))
        fig.update_layout(
            title="Potencial V(x,y) — superficie 3D interactiva (arrastra para rotar)",
            template="plotly_white",
            scene=dict(xaxis_title="x (nm)", yaxis_title="y (nm)", zaxis_title="V (meV)"),
        )
    # 'directory' deja un plotly.min.js al lado: HTML pequeño y funciona offline.
    fig.write_html(str(out), include_plotlyjs="directory")
    return out
