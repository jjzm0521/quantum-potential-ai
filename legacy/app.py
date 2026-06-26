"""
Quantum Potential — Visor / actuador (sin API).

Es un visor para el HUMANO sobre la MISMA sesión que maneja el agente con el CLI `qpot`:
lee y escribe `session/design.json`. Permite mover parámetros, resolver Schrödinger y
exportar. El "cerebro" (construir el potencial desde texto/imagen) lo hace tu agente
externo (Claude Code / ChatGPT / Codex); aquí solo se observa y se ajusta.

Uso:  python -m streamlit run app.py
"""

import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from qpot import session, render
from core.materials import list_materials

st.set_page_config(page_title="Quantum Potential — Visor", page_icon="⚛", layout="wide")
st.markdown(
    "<style>.block-container{padding-top:1rem;} .stButton>button{width:100%;}</style>",
    unsafe_allow_html=True,
)

st.title("⚛ Quantum Potential — Visor de sesión")
st.caption(
    f"Sin API. Comparte `{session.design_path()}` con el CLI `qpot` y tu agente. "
    "Construye el potencial con tu agente; aquí lo ves, lo ajustas y lo exportas."
)


# ---------------------------------------------------------------------------
# Plots (plotly, interactivos para el humano)
# ---------------------------------------------------------------------------

def plot_potential(field: dict) -> go.Figure:
    if field["dim"] == 1:
        V = field["V_eV"] * 1000.0
        fig = go.Figure(go.Scatter(x=field["x_nm"], y=V, mode="lines",
                                   line=dict(color="#1f3b73", width=2)))
        finite = V[np.isfinite(V)]
        if finite.size:
            hi, lo = np.percentile(finite, 99), np.percentile(finite, 1)
            pad = max(10.0, 0.1 * (hi - lo))
            fig.update_yaxes(range=[lo - pad, hi + pad])
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=30, b=0),
                          xaxis_title="x (nm)", yaxis_title="V (meV)", title="Potencial V(x)")
        return fig
    V = field["V_eV"] * 1000.0
    cmin, cmax = render._clip_range(V)
    Vc = np.clip(V, cmin, cmax) if cmin is not None else V
    fig = go.Figure(go.Surface(x=field["x_nm"], y=field["y_nm"], z=Vc,
                               colorscale="Viridis", cmin=cmin, cmax=cmax,
                               colorbar=dict(title="V (meV)")))
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=30, b=0),
                      title="Potencial V(x,y) — superficie 3D (arrastra para rotar)",
                      scene=dict(xaxis_title="x (nm)", yaxis_title="y (nm)",
                                 zaxis_title="V (meV)"))
    return fig


def plot_wavefunctions(res, dim: int) -> go.Figure:
    if dim == 1:
        fig = go.Figure()
        V = res.V_eV * 1000.0
        fig.add_trace(go.Scatter(x=res.x_nm, y=V, mode="lines",
                                 line=dict(color="#333", width=1.6), name="V(x)"))
        E = res.energies_meV
        n = min(4, len(E))
        amp = max(15.0, (float(np.max(E[:n])) - float(np.min(E[:n]))) / max(1, n)) if n > 1 else 40.0
        for i in range(n):
            psi = res.wavefunctions[i]
            ys = psi / (np.max(np.abs(psi)) + 1e-12) * amp + E[i]
            fig.add_trace(go.Scatter(x=res.x_nm, y=ys, mode="lines",
                                     name=f"E{i}={E[i]:.1f} meV"))
        fig.update_layout(height=440, margin=dict(l=0, r=0, t=30, b=0),
                          xaxis_title="x (nm)", yaxis_title="meV / ψ", title="Estados ligados")
        return fig
    # 2D: estado base |ψ|²
    fig = go.Figure(go.Heatmap(x=res.x_nm, y=res.y_nm, z=res.wavefunctions[0],
                               colorscale="Magma"))
    fig.update_layout(height=440, margin=dict(l=0, r=0, t=30, b=0),
                      xaxis_title="x (nm)", yaxis_title="y (nm)",
                      title=f"|ψ|² estado base · E0={res.energies_meV[0]:.1f} meV")
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


# ---------------------------------------------------------------------------
# Vista en vivo (estilo Text2CAD): re-lee la sesión y redibuja sola
# ---------------------------------------------------------------------------

@st.fragment(run_every=2)
def live_fragment() -> None:
    """Cada 2 s re-lee session/design.json del disco y redibuja, para VER cómo el
    agente construye el potencial en tiempo real (sin tocar nada tú)."""
    try:
        d = session.load_design()
    except FileNotFoundError:
        st.info("No hay sesión activa. Pídele a tu agente: `python -m qpot new --dim 1`.")
        return

    info, plot = st.columns([1, 1.4])
    with info:
        st.markdown(f"**{int(d.get('dim', 2))}D · {d.get('material', 'GaAs')} · "
                    f"{len(d.get('pieces', []))} pieza(s)**")
        for i, p in enumerate(d.get("pieces", [])):
            estado = "" if p.get("enabled", True) else " · (off)"
            st.caption(f"#{i} · {p.get('label', p.get('op'))} (`{p.get('op')}`){estado}")
        res_path = session.artifact("result.json")
        if res_path.exists():
            try:
                summ = json.loads(res_path.read_text(encoding="utf-8"))
                E = summ.get("energies_meV", [])
                if E:
                    st.markdown("**Últimos eigenvalores (meV):**")
                    st.write(" · ".join(f"{e:.1f}" for e in E[:6]))
                    st.caption(f"estados ligados: {summ.get('n_bound_states', '?')}")
            except Exception:  # noqa: BLE001
                pass
    with plot:
        try:
            field = session.evaluate_potential(d)
            st.plotly_chart(plot_potential(field), width="stretch")
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo evaluar el potencial: {exc}")


# ---------------------------------------------------------------------------
# Editor de piezas
# ---------------------------------------------------------------------------

def edit_piece(i: int, piece: dict) -> None:
    """Renderiza inputs para una pieza y aplica los cambios al dict en memoria."""
    op = piece.get("op")
    piece["enabled"] = st.checkbox("habilitada", value=piece.get("enabled", True),
                                   key=f"en_{i}")
    if "value" in piece:  # mask
        piece["value"] = st.number_input("value (eV)", value=float(piece["value"]),
                                          step=0.01, format="%.4f", key=f"val_{i}")
    _edit_args(piece.get("args", {}), prefix=f"a_{i}")
    region = piece.get("region")
    if isinstance(region, dict) and isinstance(region.get("args"), dict):
        st.caption(f"región: `{region.get('op')}`")
        _edit_args(region["args"], prefix=f"r_{i}")


def _edit_args(args: dict, prefix: str) -> None:
    for k, val in list(args.items()):
        if isinstance(val, bool):
            args[k] = st.checkbox(k, value=val, key=f"{prefix}_{k}")
        elif isinstance(val, (int, float)):
            args[k] = st.number_input(k, value=float(val), format="%.4f", key=f"{prefix}_{k}")
        elif (isinstance(val, (list, tuple)) and len(val) == 2
              and all(isinstance(c, (int, float)) for c in val)):
            c0, c1 = st.columns(2)
            x0 = c0.number_input(f"{k}[0]", value=float(val[0]), key=f"{prefix}_{k}_0")
            x1 = c1.number_input(f"{k}[1]", value=float(val[1]), key=f"{prefix}_{k}_1")
            args[k] = [x0, x1]


# ---------------------------------------------------------------------------
# Sidebar: sesión / material / dominio / nueva sesión
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Sesión")
    st.code(str(session.session_dir()), language=None)
    if st.button("🔄 Recargar desde disco"):
        st.rerun()

    live = st.toggle(
        "👁 Vista en vivo (sigue al agente)",
        help="Re-lee session/design.json cada 2 s y redibuja, para ver cómo tu agente va "
             "construyendo el potencial con `qpot`. Desactívalo para editar tú a mano.",
    )

    st.divider()
    st.subheader("Nueva sesión")
    nd_dim = st.radio("Dimensión", [1, 2], horizontal=True, key="nd_dim")
    nd_mat = st.selectbox("Material", list_materials(), key="nd_mat")
    if st.button("➕ Crear sesión vacía"):
        session.save_design(session.new_design(dim=nd_dim, material=nd_mat))
        st.success("Sesión nueva creada.")
        st.rerun()


# ---------------------------------------------------------------------------
# Carga del Design
# ---------------------------------------------------------------------------

try:
    design = session.load_design()
except FileNotFoundError:
    st.warning(
        "No hay sesión activa todavía.\n\n"
        "Créala con tu agente:  `python -m qpot new --dim 1 --material GaAs`  "
        "o con el botón **Crear sesión vacía** del panel lateral."
    )
    st.stop()

dim = int(design.get("dim", 2))

# Modo "vista en vivo": el agente está al mando, aquí solo se observa cómo cambia.
if live:
    st.caption("🔴 **En vivo** (cada 2 s). Tu agente edita con `qpot`; míralo cambiar aquí. "
               "Apaga el interruptor del panel lateral para editar tú a mano.")
    live_fragment()
    st.stop()

# Material y dominio (editables, se guardan al Design)
c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
mats = list_materials()
material = c1.selectbox("Material", mats,
                        index=mats.index(design.get("material", "GaAs"))
                        if design.get("material", "GaAs") in mats else 0)
design["material"] = material
dom = design.setdefault("domain", session.default_domain(dim))
dom["L"] = c2.number_input("Dominio L (nm)", value=float(dom.get("L", 120.0)), min_value=1.0)
dom["N"] = int(c3.number_input("Grilla N", value=int(dom.get("N", 512)), min_value=16, step=16))
n_states = int(c4.number_input("nº estados", value=6, min_value=1, max_value=30))

st.caption(f"Dimensión: **{dim}D** · {len(design.get('pieces', []))} pieza(s)")


# ---------------------------------------------------------------------------
# Cuerpo: editor (izq) + visualización (der)
# ---------------------------------------------------------------------------

left, right = st.columns([1, 1.3])

with left:
    st.subheader("Piezas del potencial")
    pieces = design.get("pieces", [])
    if not pieces:
        st.info("El Design no tiene piezas. Pídele a tu agente que las construya con `qpot add`.")
    for i, piece in enumerate(pieces):
        with st.expander(f"#{i} · {piece.get('label', piece.get('op'))} (`{piece.get('op')}`)",
                         expanded=(len(pieces) <= 3)):
            edit_piece(i, piece)
            if st.button("🗑 Eliminar pieza", key=f"del_{i}"):
                pieces.pop(i)
                session.save_design(design)
                st.rerun()

    if st.button("💾 Guardar cambios en la sesión", type="primary"):
        session.save_design(design)
        st.success("Guardado en session/design.json")

    with st.expander("Ver Design JSON"):
        st.code(json.dumps(design, ensure_ascii=False, indent=2), language="json")

with right:
    st.subheader("Potencial")
    # Aplica las ediciones (en memoria) antes de graficar.
    try:
        field = session.evaluate_potential(design)
        st.plotly_chart(plot_potential(field), width="stretch")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo evaluar el potencial: {exc}")

    issues = session.validation_issues(design)
    if issues:
        st.warning("Validación:\n- " + "\n- ".join(issues))
    else:
        st.success("Validación OK.")

    if st.button("▶ Resolver Schrödinger", type="primary"):
        session.save_design(design)  # la sesión es la fuente de verdad
        with st.spinner("Resolviendo..."):
            res, summary = session.solve_design(design, n_states=n_states)
        st.session_state["solve"] = summary
        st.plotly_chart(plot_wavefunctions(res, dim), width="stretch")
        cols = st.columns(min(4, summary["n_states"]))
        for k, E in enumerate(summary["energies_meV"][:len(cols)]):
            cols[k].metric(f"E{k}", f"{E:.2f} meV")
        st.caption(f"Convergencia: {'✅' if summary['convergence_ok'] else '⚠'} · "
                   f"estados ligados: {summary['n_bound_states']}")


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Exportar a COMSOL / resultados")
ec = st.columns(5)
labels = {"m": "📄 Script .m", "mph": "📦 .mph", "csv": "🔢 CSV",
          "npz": "🧮 NumPy .npz", "recipe": "📋 Receta"}
for col, fmt in zip(ec, ["m", "mph", "csv", "npz", "recipe"]):
    if col.button(labels[fmt], key=f"exp_{fmt}"):
        session.save_design(design)
        with st.spinner(f"Exportando {fmt}..."):
            path, msg = session.export_design(design, fmt, n_states=n_states)
        (st.success if path else st.error)(msg)
        if path:
            st.caption(f"Archivo: {path}")
