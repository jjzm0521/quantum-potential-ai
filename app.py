"""
Quantum Potential AI — Interfaz Streamlit (1D + 2D Catálogo + 2D Designer)
Uso: streamlit run app.py
"""

import os
import json
import io
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

load_dotenv()

from core.materials    import MATERIALS, list_materials
from core.potentials   import POTENTIALS, evaluate, list_potentials
from core.potentials_1d import POTENTIALS_1D, evaluate_1d, list_potentials_1d
from core.solver       import solve,    make_grid
from core.solver_1d    import solve_1d, make_grid_1d
from core.exporter     import to_csv, to_npz, to_comsol_m, to_comsol_m_1d
from core.primitives   import (
    REGION_PRIMITIVES, PROFILE_PRIMITIVES, ALL_PRIMITIVES,
    list_regions, list_profiles,
)
from core.primitives_dsl_1d import (
    REGION_PRIMITIVES_1D, PROFILE_PRIMITIVES_1D, ALL_PRIMITIVES_1D,
    list_regions_1d, list_profiles_1d,
)
from core.composer     import (
    evaluate_design, design_to_matlab_expr, preset_to_design,
    evaluate_design_1d, design_to_matlab_expr_1d,
)
from core.exporter_mph import mph_available, export_mph_or_fallback


# ===========================================================================
st.set_page_config(
    page_title="Quantum Potential AI",
    page_icon="⚛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container { padding-top: 0.5rem; padding-bottom: 0rem; }
.stButton>button { width: 100%; }
h1 { font-size: 1.6rem !important; margin-bottom: 0 !important; }
h3 { font-size: 1.0rem !important; margin-top: 0.5rem !important; }
.stAlert { font-size: 0.85rem; }
[data-testid="stMetricValue"] { font-size: 1.05rem !important; }
.piece-card { background:#1A1F2E; padding:0.6rem 0.8rem; border-radius:6px;
              border-left:3px solid #4A90D9; margin-bottom:0.4rem; }
.small-caption { font-size: 0.78rem; color: #888; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "mode": "2D Designer (IA)",   # default al modo nuevo
        "ai_result_legacy": None,
        "solver_result": None,
        # catálogo 1D
        "current_pot_1d": "finite_well",
        "current_params_1d": dict(POTENTIALS_1D["finite_well"].params),
        # catálogo 2D
        "current_pot_2d": "quantum_dot",
        "current_params_2d": dict(POTENTIALS["quantum_dot"].params),
        # designer 2D (DSL)
        "design": {
            "dim": 2,
            "material": "GaAs",
            "domain": {"L": 200.0, "N": 96},
            "pieces": [
                {"label": "anillo cuántico",
                 "op": "mexican_hat",
                 "args": {"center":[0.0,0.0], "r0":40.0, "depth":0.3}},
            ],
        },
        # designer 1D (DSL)
        "design_1d": {
            "dim": 1,
            "material": "GaAs",
            "domain": {"L": 120.0, "N": 1024},
            "pieces": [
                {"label": "pozo finito 30nm",
                 "op": "mask",
                 "region": {"op": "interval", "args": {"center":0.0, "length":30.0}},
                 "value": -0.25},
            ],
        },
        "pipeline_result": None,
        # común
        "current_material": "GaAs",
        "grid_N_1d": 512,
        "grid_L_1d": 120.0,
        "grid_N_2d": 96,
        "grid_L_2d": 200.0,
        "n_states": 6,
        "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "enable_verifier": True,
        "enable_refiner":  True,
        "agent_task_id": "",
        "agent_task_goal": "",
        "agent_source_text": "",
        "agent_source_image_bytes": None,
        "agent_source_image_mime": "",
        "agent_source_image_name": "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

_init_state()


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

def _plot_potential_2d(V_eV, x_nm, y_nm, title="Potencial V(x,y)"):
    X, Y = np.meshgrid(x_nm, y_nm)
    V_plot = np.clip(V_eV, np.percentile(V_eV,1), np.percentile(V_eV,99))
    fig = go.Figure(data=[go.Surface(
        x=X, y=Y, z=V_plot, colorscale="RdBu_r",
        colorbar=dict(title="eV", thickness=12, len=0.7),
    )])
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0), height=360,
        scene=dict(xaxis_title="x (nm)", yaxis_title="y (nm)", zaxis_title="V (eV)",
                   camera=dict(eye=dict(x=1.4, y=-1.4, z=1.0))),
        title=dict(text=title, font=dict(size=13)),
    )
    return fig


def _plot_potential_2d_heatmap(V_eV, x_nm, y_nm, title="V(x,y) — vista superior"):
    V_plot = np.clip(V_eV, np.percentile(V_eV,1), np.percentile(V_eV,99))
    fig = go.Figure(data=go.Heatmap(
        x=x_nm, y=y_nm, z=V_plot, colorscale="RdBu_r",
        colorbar=dict(title="eV", thickness=12, len=0.7),
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0), height=320,
        xaxis_title="x (nm)", yaxis_title="y (nm)",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        title=dict(text=title, font=dict(size=13)),
    )
    return fig


def _plot_wavefunctions_2d(result, n_show=4):
    n = min(n_show, len(result.energies_meV))
    cols = 2
    rows = (n + 1) // cols
    titles = [f"ψ{i} — E={result.energies_meV[i]:.2f} meV" for i in range(n)]
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles)
    for i in range(n):
        r, c = divmod(i, cols)
        fig.add_trace(go.Heatmap(
            x=result.x_nm, y=result.y_nm,
            z=result.wavefunctions[i], colorscale="Viridis",
            showscale=(i == 0),
            colorbar=dict(title="|ψ|²", thickness=10, len=0.4),
        ), row=r+1, col=c+1)
    fig.update_layout(height=200*rows+40, margin=dict(l=0,r=0,t=35,b=0),
                      title=dict(text="Funciones de onda |ψ|²", font=dict(size=13)))
    return fig


def _plot_textbook_1d(V_eV, x_nm, result=None, V_clip=None):
    fig = go.Figure()
    V_show = np.clip(V_eV*1000, *V_clip) if V_clip else V_eV*1000
    fig.add_trace(go.Scatter(x=x_nm, y=V_show, mode="lines",
                              line=dict(color="white", width=2), name="V(x)"))
    if result is not None:
        n = len(result.energies_meV)
        colors = ["#FF6B6B","#4ECDC4","#FFE66D","#A8E6CF","#C7B8EA","#FFB4A2","#B5EAD7","#FFDAC1"]
        V_range = V_show.max() - V_show.min()
        psi_scale = V_range / (n * 4)
        for i in range(n):
            E = result.energies_meV[i]
            psi = result.wavefunctions[i]
            peak = np.max(np.abs(psi))
            psi_plot = psi*psi_scale/peak + E if peak>0 else np.full_like(psi, E)
            color = colors[i%len(colors)]
            fig.add_trace(go.Scatter(x=[x_nm[0],x_nm[-1]], y=[E,E], mode="lines",
                                      line=dict(color=color,width=1,dash="dot"),
                                      name=f"E{i}={E:.2f} meV", showlegend=True))
            fig.add_trace(go.Scatter(x=x_nm, y=psi_plot, mode="lines",
                                      line=dict(color=color,width=2), showlegend=False))
    fig.update_layout(height=480, margin=dict(l=0,r=0,t=35,b=30),
                      title=dict(text="V(x) y funciones de onda ψₙ(x)", font=dict(size=13)),
                      xaxis_title="x (nm)", yaxis_title="Energía (meV)",
                      legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0.3)"),
                      hovermode="x unified")
    return fig


# ===========================================================================
# Helpers comunes a 1D y 2D Designer (declarados ANTES de usarse)
# ===========================================================================

def _editor_kind() -> str:
    """Devuelve 'design' o 'design_1d' según el modo activo."""
    return "design_1d" if st.session_state.mode == "1D Designer (IA)" else "design"


def _is_1d_designer() -> bool:
    return st.session_state.mode == "1D Designer (IA)"

def _step_for(arg_name: str) -> float:
    n = arg_name.lower()
    if n in ("depth", "amplitude", "height", "value"): return 0.01
    if "sigma" in n or "width" in n or "r0" in n: return 1.0
    if n.startswith("omega"): return 0.0001
    if n in ("slope", "force"): return 0.0001
    if n == "regularization": return 0.1
    if n == "eps_r": return 0.1
    if n == "alpha": return 0.005
    if n == "n": return 0.5
    if n == "k": return 1.0
    return 0.1


def _edit_region(region: dict, key_prefix: str):
    if _is_1d_designer():
        regions_list_fn = list_regions_1d
        REGS = REGION_PRIMITIVES_1D
        default_first = regions_list_fn()[0]
    else:
        regions_list_fn = list_regions
        REGS = REGION_PRIMITIVES
        default_first = "disk"
    op = region.get("op", default_first)
    regs = regions_list_fn()
    region["op"] = st.selectbox("op", regs,
                                  index=regs.index(op) if op in regs else 0,
                                  key=f"{key_prefix}_op")
    spec = REGS[region["op"]]
    args = region.setdefault("args", dict(spec.args))
    for arg_name, default in spec.args.items():
        cur = args.get(arg_name, default)
        if isinstance(default, (int, float)):
            args[arg_name] = st.number_input(arg_name, value=float(cur), step=1.0,
                                                key=f"{key_prefix}_{arg_name}")
        elif isinstance(default, list) and len(default) == 2:
            c1, c2 = st.columns(2)
            with c1:
                x = st.number_input(f"{arg_name}.x", value=float(cur[0]), step=1.0,
                                     key=f"{key_prefix}_{arg_name}_x")
            with c2:
                y = st.number_input(f"{arg_name}.y", value=float(cur[1]), step=1.0,
                                     key=f"{key_prefix}_{arg_name}_y")
            args[arg_name] = [float(x), float(y)]
        elif isinstance(default, str):
            args[arg_name] = st.text_input(arg_name, value=str(cur),
                                             key=f"{key_prefix}_{arg_name}")


def _edit_piece_args(piece: dict, i: int):
    op = piece.get("op")
    PROFS = PROFILE_PRIMITIVES_1D if _is_1d_designer() else PROFILE_PRIMITIVES
    if op == "mask":
        st.markdown("**Región:**")
        _edit_region(piece["region"], f"piece_{i}_region")
        piece["value"] = st.number_input("value (eV)",
                                          value=float(piece.get("value", 0.0)),
                                          step=0.01, key=f"piece_{i}_value")
        return
    if op == "where":
        st.caption("Edición de 'where' por ahora vía JSON crudo (sección de abajo).")
        return
    spec = PROFS.get(op)
    if spec is None:
        st.warning(f"Op '{op}' no editable inline. Usa JSON crudo.")
        return
    args = piece.setdefault("args", dict(spec.args))
    for arg_name, default in spec.args.items():
        unit = spec.arg_units.get(arg_name, "")
        cur = args.get(arg_name, default)
        if isinstance(default, (int, float)):
            new = st.number_input(
                f"{arg_name} [{unit}]" if unit else arg_name,
                value=float(cur), step=_step_for(arg_name),
                key=f"piece_{i}_{arg_name}",
            )
            args[arg_name] = float(new)
        elif isinstance(default, list) and len(default) == 2:
            c1, c2 = st.columns(2)
            with c1:
                x = st.number_input(f"{arg_name}.x", value=float(cur[0]),
                                     step=1.0, key=f"piece_{i}_{arg_name}_x")
            with c2:
                y = st.number_input(f"{arg_name}.y", value=float(cur[1]),
                                     step=1.0, key=f"piece_{i}_{arg_name}_y")
            args[arg_name] = [float(x), float(y)]
        elif isinstance(default, str):
            args[arg_name] = st.text_input(arg_name, value=str(cur),
                                             key=f"piece_{i}_{arg_name}")
        elif isinstance(default, list):  # vertices, coeffs
            txt = st.text_area(
                f"{arg_name} (JSON)",
                value=json.dumps(cur), height=80, key=f"piece_{i}_{arg_name}",
            )
            try:
                args[arg_name] = json.loads(txt)
            except Exception:
                st.error(f"{arg_name}: JSON inválido")


def _render_pieces_editor():
    key = _editor_kind()
    PROFS = PROFILE_PRIMITIVES_1D if _is_1d_designer() else PROFILE_PRIMITIVES
    REGS  = REGION_PRIMITIVES_1D  if _is_1d_designer() else REGION_PRIMITIVES
    list_profs_fn = list_profiles_1d if _is_1d_designer() else list_profiles
    list_regs_fn  = list_regions_1d  if _is_1d_designer() else list_regions
    default_region = "interval" if _is_1d_designer() else "disk"
    default_region_args = ({"center":0.0,"length":20.0} if _is_1d_designer()
                            else {"center":[0,0],"radius":30})
    pieces = st.session_state[key].get("pieces", [])
    to_delete = None
    for i, piece in enumerate(pieces):
        with st.container():
            st.markdown(f'<div class="piece-card">', unsafe_allow_html=True)
            h1, h2, h3 = st.columns([3,1,1])
            with h1:
                label = piece.get("label", piece.get("op","?"))
                st.markdown(f"**#{i+1}. {piece.get('op','?')}** — _{label}_")
            with h2:
                piece["enabled"] = st.checkbox("on", value=piece.get("enabled", True),
                                                 key=f"enabled_{i}", label_visibility="collapsed")
            with h3:
                if st.button("🗑", key=f"del_{i}", help="Eliminar pieza"):
                    to_delete = i
            with st.expander("Editar parámetros"):
                _edit_piece_args(piece, i)
            st.markdown('</div>', unsafe_allow_html=True)
    if to_delete is not None:
        del pieces[to_delete]
        st.rerun()

    with st.expander("➕ Agregar pieza nueva"):
        new_kind = st.radio("Tipo", ["Perfil", "mask", "where"],
                             key=f"new_piece_kind_{key}", horizontal=True)
        if new_kind == "Perfil":
            new_op = st.selectbox("Operación", list_profs_fn(),
                                    key=f"new_piece_op_{key}")
            if st.button("Agregar pieza", key=f"add_profile_{key}"):
                spec = PROFS[new_op]
                pieces.append({"op": new_op, "args": dict(spec.args),
                                "label": new_op, "enabled": True})
                st.rerun()
        elif new_kind == "mask":
            region_op = st.selectbox("Región", list_regs_fn(),
                                       key=f"new_mask_region_{key}")
            value = st.number_input("Valor (eV)", value=-0.1, step=0.01,
                                      key=f"new_mask_val_{key}")
            if st.button("Agregar mask", key=f"add_mask_{key}"):
                reg_spec = REGS[region_op]
                pieces.append({"op": "mask",
                                "region": {"op": region_op, "args": dict(reg_spec.args)},
                                "value": float(value),
                                "label": f"mask {region_op}", "enabled": True})
                st.rerun()
        elif new_kind == "where":
            if st.button("Agregar where (plantilla)", key=f"add_where_{key}"):
                pieces.append({
                    "op": "where",
                    "region": {"op": default_region, "args": dict(default_region_args)},
                    "inner": {"op": "constant", "args": {"value": -0.3}},
                    "outer": {"op": "constant", "args": {"value": 0.0}},
                    "label": "where", "enabled": True,
                })
                st.rerun()

    with st.expander("👨‍💻 Ver / editar JSON crudo"):
        edited = st.text_area("Design JSON",
                                value=json.dumps(st.session_state[key],
                                                  indent=2, ensure_ascii=False),
                                height=240, key=f"design_json_raw_{key}")
        if st.button("Aplicar JSON", key=f"apply_json_{key}"):
            try:
                st.session_state[key] = json.loads(edited)
                st.rerun()
            except Exception as e:
                st.error(f"JSON inválido: {e}")


def _run_solver_designer():
    if _is_1d_designer():
        design = st.session_state.design_1d
        L = design["domain"]["L"]; N = design["domain"]["N"]
        x_nm = make_grid_1d(L, N)
        V_eV = evaluate_design_1d(design, x_nm)
        mat = MATERIALS[st.session_state.current_material]
        try:
            res = solve_1d(V_eV, x_nm, mat.m_eff, st.session_state.n_states)
            st.session_state.solver_result = res
        except Exception as e:
            st.error(f"Error solver 1D: {e}")
    else:
        design = st.session_state.design
        L = design["domain"]["L"]; N = design["domain"]["N"]
        x_nm, y_nm, X, Y = make_grid(L, N)
        V_eV = evaluate_design(design, X, Y)
        mat = MATERIALS[st.session_state.current_material]
        try:
            res = solve(V_eV, x_nm, y_nm, mat.m_eff, st.session_state.n_states)
            st.session_state.solver_result = res
        except Exception as e:
            st.error(f"Error solver: {e}")


def _render_mph_export(design: dict, mat_key: str, mat, key_suffix: str):
    mph_ok, _ = mph_available()
    if st.button("📦 Generar .mph", disabled=not mph_ok,
                   help="Genera archivo COMSOL directo (requiere MPh)",
                   key=f"btn_mph_{key_suffix}"):
        with st.spinner("Generando .mph con COMSOL..."):
            filename = f"quantum_potential_{key_suffix}.mph"
            path, msg = export_mph_or_fallback(
                design, mat_key, mat.m_eff,
                st.session_state.n_states, filename
            )
            if path:
                st.success(msg)
                with open(path, "rb") as f:
                    st.download_button("Descargar .mph", f.read(),
                                        filename,
                                        "application/octet-stream",
                                        key=f"download_mph_{key_suffix}")
            else:
                st.error(msg)


def _render_comsol_recipe_expander(design: dict, key_suffix: str):
    with st.expander("📋 Receta de construcción para COMSOL (Paso a Paso)", expanded=False):
        from core.composer import generate_comsol_recipe
        try:
            recipe_md = generate_comsol_recipe(design)
            st.markdown(recipe_md)
        except Exception as e:
            st.error(f"No se pudo generar la receta de COMSOL: {e}")


def _run_pipeline_text(description: str):
    from ai.pipeline import run_pipeline_from_text
    force_dim = 1 if _is_1d_designer() else 2
    target_key = "design_1d" if _is_1d_designer() else "design"
    with st.spinner(f"Pipeline IA ({force_dim}D): designer → verifier → refiner..."):
        try:
            result = run_pipeline_from_text(
                description,
                enable_verifier=st.session_state.enable_verifier,
                enable_refiner=st.session_state.enable_refiner,
                force_dim=force_dim,
            )
            st.session_state.pipeline_result = result
            if result.final_design and result.final_design.get("pieces"):
                st.session_state[target_key] = result.final_design
            st.rerun()
        except Exception as e:
            st.error(f"Pipeline falló: {e}")


def _run_pipeline_image(img_bytes: bytes, mime: str, extra_ctx: str):
    from ai.pipeline import run_pipeline_from_image
    force_dim = 1 if _is_1d_designer() else 2
    target_key = "design_1d" if _is_1d_designer() else "design"
    with st.spinner(f"Pipeline IA ({force_dim}D): designer → verifier → refiner..."):
        try:
            result = run_pipeline_from_image(
                img_bytes, mime, extra_ctx,
                enable_verifier=st.session_state.enable_verifier,
                enable_refiner=st.session_state.enable_refiner,
                force_dim=force_dim,
            )
            st.session_state.pipeline_result = result
            if result.final_design and result.final_design.get("pieces"):
                st.session_state[target_key] = result.final_design
            st.rerun()
        except Exception as e:
            st.error(f"Pipeline falló: {e}")


def _render_pipeline_trace(result):
    converged_emoji = "🟢" if result.converged else "🟡"
    if result.error:
        st.error(f"❌ Pipeline error: {result.error}")
        return
    st.markdown(f"### {converged_emoji} Resultado IA — score {result.final_score}/10  "
                 f"(confianza: {result.final_confidence})")
    for it in result.iterations:
        label = "Designer inicial" if it.iteration == 0 else f"Refinador iter {it.iteration}"
        with st.expander(f"📋 {label}" +
                          (f"  ·  score {it.verifier.score}/10" if it.verifier else "")):
            if it.iteration == 0:
                st.markdown("**Análisis del agente:**")
                st.write(it.reasoning)
            else:
                st.markdown("**Razonamiento del refinador:**")
                st.write(it.reasoning)
                if it.changes_summary:
                    st.markdown("**Cambios aplicados:**")
                    st.code(it.changes_summary)
            if it.validator_issues:
                st.markdown("**⚠ Validador numérico:**")
                for iss in it.validator_issues:
                    st.warning(iss)
            if it.verifier:
                v = it.verifier
                cmatch, cmiss = st.columns(2)
                with cmatch:
                    st.markdown("**✅ Coincide:**")
                    for m in v.matches: st.write(f"- {m}")
                with cmiss:
                    st.markdown("**⚠ No coincide:**")
                    for m in v.mismatches: st.write(f"- {m}")
                if v.suggestions:
                    st.markdown("**💡 Sugerencias del verificador:**")
                    for s in v.suggestions: st.write(f"- {s}")
                st.markdown("**Render visto por el verificador:**")
                st.image(v.render_png, width=320)
    if result.designer_output and result.designer_output.self_critique:
        with st.expander("🔍 Auto-crítica del designer"):
            st.write(result.designer_output.self_critique)


def _latest_verifier_render() -> bytes | None:
    result = st.session_state.get("pipeline_result")
    if not result:
        return None
    for it in reversed(result.iterations):
        if it.verifier and it.verifier.render_png:
            return it.verifier.render_png
    return None


def _remember_agent_text(text: str):
    st.session_state.agent_source_text = text.strip()


def _remember_agent_image(img_bytes: bytes, mime: str, name: str = ""):
    st.session_state.agent_source_image_bytes = img_bytes
    st.session_state.agent_source_image_mime = mime
    st.session_state.agent_source_image_name = name


def _agent_image_ext() -> str:
    mime = st.session_state.get("agent_source_image_mime", "")
    name = st.session_state.get("agent_source_image_name", "")
    if name and "." in name:
        return name.rsplit(".", 1)[-1].lower()
    if "jpeg" in mime or "jpg" in mime:
        return "jpg"
    if "tiff" in mime:
        return "tiff"
    return "png"


def _agent_task_description() -> str:
    parts = []
    if st.session_state.agent_task_goal.strip():
        parts.append("Objetivo del agente:\n" + st.session_state.agent_task_goal.strip())
    if st.session_state.agent_source_text.strip():
        parts.append("Texto/contexto fuente:\n" + st.session_state.agent_source_text.strip())
    if st.session_state.agent_source_image_name:
        parts.append(f"Imagen fuente adjunta: {st.session_state.agent_source_image_name}")
    return "\n\n".join(parts)


def _render_agent_harness():
    from ai.agent_harness import (
        available_agent_tools,
        agent_tool_presets,
        external_execution_enabled,
        list_agent_tasks,
        load_agent_result,
        prepare_agent_task,
        render_command,
        run_agent_tool,
        run_design_review,
        run_local_calculation,
        tasks_root,
    )

    design_key = _editor_kind()
    design = st.session_state[design_key]

    with st.expander("🧰 Harness de agentes externos y cálculo local", expanded=False):
        st.caption(
            "Prepara una tarea para Codex, Claude, Antigravity u otro agente. "
            "También puede validar y resolver localmente sin gastar API."
        )
        st.session_state.agent_task_goal = st.text_area(
            "Objetivo para el agente",
            value=st.session_state.agent_task_goal,
            placeholder=(
                "Ej: revisa si este Design es físicamente plausible, ajusta piezas "
                "si hace falta y devuelve result.json."
            ),
            height=90,
            key=f"agent_goal_{design_key}",
        )

        with st.expander("Contexto que recibirá el agente"):
            st.session_state.agent_source_text = st.text_area(
                "Texto o notas de referencia",
                value=st.session_state.agent_source_text,
                placeholder="Descripción experimental, escala de la imagen, material, restricciones, parámetros deseados...",
                height=90,
                key=f"agent_source_text_{design_key}",
            )
            ref_img = st.file_uploader(
                "Imagen de referencia para el agente",
                type=["png", "jpg", "jpeg", "tif", "tiff"],
                key=f"agent_ref_image_{design_key}",
            )
            if ref_img is not None:
                img_bytes = ref_img.getvalue()
                mime = "image/png" if ref_img.name.lower().endswith("png") else "image/jpeg"
                if ref_img.name.lower().endswith(("tif", "tiff")):
                    mime = "image/tiff"
                _remember_agent_image(img_bytes, mime, ref_img.name)
            if st.session_state.agent_source_image_bytes:
                st.caption(f"Imagen lista para adjuntar: `{st.session_state.agent_source_image_name or 'imagen'}`")
            else:
                st.caption("Sin imagen adjunta para el agente.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Preparar tarea", key=f"prepare_agent_task_{design_key}"):
                try:
                    task = prepare_agent_task(
                        design,
                        description=_agent_task_description(),
                        n_states=st.session_state.n_states,
                        original_image=st.session_state.agent_source_image_bytes,
                        original_image_ext=_agent_image_ext(),
                        render_png=_latest_verifier_render(),
                    )
                    st.session_state.agent_task_id = task.task_id
                    st.success(f"Tarea creada: {task.task_id}")
                except Exception as e:
                    st.error(f"No se pudo crear la tarea: {e}")
        with c2:
            st.caption(f"Carpeta base: `{tasks_root()}`")

        tasks = list_agent_tasks()
        if not tasks:
            st.info("Todavía no hay tareas de agente.")
            return

        task_ids = [t["task_id"] for t in tasks]
        current = st.session_state.agent_task_id if st.session_state.agent_task_id in task_ids else task_ids[0]
        selected = st.selectbox(
            "Tarea activa",
            task_ids,
            index=task_ids.index(current),
            format_func=lambda tid: f"{tid} {'✓ result.json' if next(t for t in tasks if t['task_id'] == tid)['has_result'] else ''}",
            key=f"agent_task_select_{design_key}",
        )
        st.session_state.agent_task_id = selected
        selected_meta = next(t for t in tasks if t["task_id"] == selected)
        st.code(selected_meta["dir"], language="text")

        h1, h2, h3 = st.columns(3)
        with h1:
            if st.button("Revisar parametrización", key=f"agent_design_review_{design_key}"):
                with st.spinner("Revisando descripción paramétrica..."):
                    try:
                        result = run_design_review(selected)
                        st.success("Revisión de parametrización terminada.")
                        st.json(result.get("diagnostics", {}).get("design_contract", {}))
                    except Exception as e:
                        st.error(f"Revisión falló: {e}")
            if st.button("Correr cálculo local", key=f"agent_local_calc_{design_key}"):
                with st.spinner("Validando y resolviendo localmente..."):
                    try:
                        result = run_local_calculation(selected)
                        st.success("Cálculo local terminado.")
                        st.json(result.get("diagnostics", {}))
                    except Exception as e:
                        st.error(f"Cálculo local falló: {e}")

        tools = available_agent_tools()
        with h2:
            if tools:
                tool_names = [t.name for t in tools]
                tool_name = st.selectbox("Herramienta externa", tool_names,
                                         key=f"agent_tool_{design_key}")
                tool = next(t for t in tools if t.name == tool_name)
                st.caption(f"Config: `{tool.env_name}`")
            else:
                tool_name = ""
                tool = None
                st.caption("Configura `AGENT_TOOL_CODEX`, `AGENT_TOOL_CLAUDE` o `AGENT_TOOL_ANTIGRAVITY`.")
                with st.expander("Presets para copiar en .env"):
                    for preset in agent_tool_presets():
                        if preset["detected_on_path"]:
                            detected = f"comando detectado: {preset['detected_path']}"
                        elif preset["local_config_found"]:
                            detected = "instalación/configuración encontrada, falta comando en PATH"
                        else:
                            detected = "no detectado"
                        st.caption(f"{preset['name']} ({detected})")
                        st.code(
                            f"{preset['env_name']}={preset['command_template']}",
                            language="bash",
                        )
                    st.code("AGENT_HARNESS_ENABLE_RUN=1", language="bash")

        with h3:
            if tool:
                if external_execution_enabled():
                    if st.button("Ejecutar herramienta", key=f"agent_run_tool_{design_key}"):
                        with st.spinner(f"Ejecutando {tool.name}..."):
                            try:
                                run = run_agent_tool(tool.name, selected)
                                if run.ok:
                                    st.success("Herramienta terminada sin error.")
                                else:
                                    st.error(f"La herramienta terminó con código {run.returncode}.")
                                if run.stdout:
                                    st.text_area("Salida", run.stdout[-4000:], height=120)
                                if run.stderr:
                                    st.text_area("Errores", run.stderr[-4000:], height=120)
                            except Exception as e:
                                st.error(f"No se pudo ejecutar la herramienta: {e}")
                else:
                    st.caption("Ejecución desactivada. Usa `AGENT_HARNESS_ENABLE_RUN=1` para permitirla.")

        if tool:
            with st.expander("Comando preparado"):
                try:
                    st.code(render_command(tool, selected), language="bash")
                except Exception as e:
                    st.error(f"No se pudo preparar el comando: {e}")

        if selected_meta["has_result"]:
            st.markdown("**Resultado disponible**")
            try:
                result, issues = load_agent_result(selected)
                st.json({
                    "status": result.get("status"),
                    "confidence": result.get("confidence"),
                    "changes_summary": result.get("changes_summary"),
                    "validator_issues": issues,
                })
                if st.button("Aplicar result.json al Design actual",
                             key=f"agent_apply_result_{design_key}"):
                    if not isinstance(result.get("design"), dict):
                        st.error("El result.json no contiene un Design válido.")
                    else:
                        st.session_state[design_key] = result["design"]
                        st.success("Design actualizado desde result.json.")
                        st.rerun()
            except Exception as e:
                st.error(f"No se pudo leer result.json: {e}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Configuración")
    api_key = st.text_input("ANTHROPIC_API_KEY",
                            value=os.environ.get("ANTHROPIC_API_KEY",""),
                            type="password")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        st.session_state.api_key_set = True

    st.divider()
    st.markdown("**Pipeline IA**")
    st.session_state.enable_verifier = st.checkbox(
        "Activar verificador visual", value=st.session_state.enable_verifier,
        help="Compara el render con la imagen original")
    st.session_state.enable_refiner = st.checkbox(
        "Activar refinador iterativo", value=st.session_state.enable_refiner,
        help="Itera hasta 3 veces para mejorar el Design (score ≥ 7)")

    st.divider()
    st.markdown("**Grilla y solver**")
    if st.session_state.mode == "1D Catálogo":
        st.session_state.grid_N_1d = st.select_slider(
            "Resolución 1D", [128,256,512,1024,2048], st.session_state.grid_N_1d)
        st.session_state.grid_L_1d = st.slider("Dominio (nm)", 40.0, 500.0,
                                                st.session_state.grid_L_1d, 5.0)
    else:
        st.session_state.grid_N_2d = st.select_slider(
            "Resolución 2D", [48,64,96,128,192,256], st.session_state.grid_N_2d)
        st.session_state.grid_L_2d = st.slider("Dominio (nm)", 80.0, 600.0,
                                                st.session_state.grid_L_2d, 10.0)
    st.session_state.n_states = st.slider("Nº de estados", 2, 12, st.session_state.n_states)

    st.divider()
    mph_ok, mph_msg = mph_available()
    st.caption(f"**MPh (COMSOL directo):** {'✅' if mph_ok else '❌'}")
    st.caption(mph_msg)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
hcol1, hcol2 = st.columns([3,2])
with hcol1:
    st.markdown("# ⚛ Quantum Potential AI")
    st.caption("Describe o sube imagen → IA compone potencial → solver Schrödinger → resultados")
with hcol2:
    MODES = ["1D Catálogo", "1D Designer (IA)", "2D Catálogo", "2D Designer (IA)"]
    if st.session_state.mode not in MODES:
        st.session_state.mode = MODES[1]
    st.session_state.mode = st.radio(
        "Modo", options=MODES,
        index=MODES.index(st.session_state.mode),
        horizontal=True,
    )

MODE = st.session_state.mode


# ===========================================================================
# MODO 1: 1D Catálogo (igual que antes)
# ===========================================================================
if MODE == "1D Catálogo":
    col_left, col_right = st.columns([1, 1.4], gap="medium")
    pot_keys = list_potentials_1d()
    pot_labels = {k: POTENTIALS_1D[k].label for k in pot_keys}

    with col_left:
        st.markdown("### 1️⃣ Potencial 1D")
        cur = st.session_state.current_pot_1d
        if cur not in pot_keys: cur = pot_keys[0]
        pot_choice = st.selectbox("Tipo", pot_keys,
                                   format_func=lambda k: pot_labels[k],
                                   index=pot_keys.index(cur))
        if pot_choice != st.session_state.current_pot_1d:
            st.session_state.current_pot_1d = pot_choice
            st.session_state.current_params_1d = dict(POTENTIALS_1D[pot_choice].params)
        st.caption(POTENTIALS_1D[pot_choice].description)

        st.markdown("### 2️⃣ Material")
        mat_key = st.selectbox("Semiconductor", list_materials(),
                                index=list_materials().index(st.session_state.current_material),
                                format_func=lambda k:f"{k}  (m*={MATERIALS[k].m_eff} mₑ)")
        st.session_state.current_material = mat_key
        mat = MATERIALS[mat_key]

        st.markdown("### 3️⃣ Parámetros")
        pdef = POTENTIALS_1D[st.session_state.current_pot_1d]
        updated = {}
        for pname, default in pdef.params.items():
            lo, hi, step = pdef.param_ranges[pname]
            unit = pdef.param_units.get(pname, "")
            cur = float(np.clip(
                st.session_state.current_params_1d.get(pname, default), lo, hi))
            updated[pname] = st.slider(
                f"{pname} [{unit}]", float(lo), float(hi), cur, float(step),
                key=f"slider_1d_{pname}",
            )
        st.session_state.current_params_1d = updated

        run_btn = st.button("▶ Correr solver Schrödinger 1D", type="primary")

    with col_right:
        N = st.session_state.grid_N_1d
        L = st.session_state.grid_L_1d
        x_nm = make_grid_1d(L, N)
        V_eV = evaluate_1d(st.session_state.current_pot_1d, x_nm,
                            st.session_state.current_params_1d)
        V_max_show = max(50.0,
                          (np.percentile(V_eV[V_eV<100],99)*1000*1.5)
                          if np.any(V_eV<100) else 50.0)
        V_min_show = (np.min(V_eV)*1000) - 20.0

        fig = _plot_textbook_1d(V_eV, x_nm,
                                 result=st.session_state.solver_result
                                 if (st.session_state.solver_result is not None
                                     and not hasattr(st.session_state.solver_result, "grid_size"))
                                 else None,
                                 V_clip=(V_min_show, V_max_show))
        st.plotly_chart(fig, use_container_width=True, key="textbook_1d")

        if run_btn:
            with st.spinner("Resolviendo..."):
                try:
                    res = solve_1d(V_eV, x_nm, mat.m_eff, st.session_state.n_states)
                    st.session_state.solver_result = res
                    st.rerun()
                except Exception as e:
                    st.error(f"Error solver: {e}")

        res = st.session_state.solver_result
        if res is not None and not hasattr(res, "grid_size"):
            st.markdown("### Eigenvalores")
            cols_e = st.columns(min(len(res.energies_meV), 4))
            for i, (col, E) in enumerate(zip(cols_e, res.energies_meV)):
                col.metric(f"E{i}", f"{E:.2f} meV")
            pdef = POTENTIALS_1D[st.session_state.current_pot_1d]
            if pdef.analytic_E is not None:
                try:
                    E_ana = pdef.analytic_E(st.session_state.current_params_1d, mat.m_eff)
                    with st.expander("📐 Validación con solución analítica"):
                        for i in range(min(len(res.energies_meV), len(E_ana))):
                            num, ana = res.energies_meV[i], E_ana[i]
                            err = abs(num-ana)/abs(ana)*100 if ana!=0 else 0
                            st.write(f"E{i}: num={num:.4f} | ana={ana:.4f} | err={err:.3f}%")
                except Exception:
                    pass

            st.markdown("### Exportar")
            d1,d2,d3,d4 = st.columns(4)
            with d1: st.download_button("📄 CSV", to_csv(res),
                                          "eigenvalores_1d.csv", "text/csv")
            with d2: st.download_button("🔢 NumPy", to_npz(res),
                                          "wavefunctions_1d.npz", "application/octet-stream")
            with d3: st.download_button("🔧 COMSOL .m",
                                          to_comsol_m_1d(res, st.session_state.current_pot_1d,
                                                          st.session_state.current_params_1d,
                                                          mat_key, mat.m_eff, "V_manual"),
                                          "comsol_1d.m", "text/plain")
            with d4:
                cat_design = preset_to_design(st.session_state.current_pot_1d,
                                              st.session_state.current_params_1d, dim=1)
                cat_design["domain"] = {"L": st.session_state.grid_L_1d, "N": st.session_state.grid_N_1d}
                _render_mph_export(cat_design, mat_key, mat, "cat_1d")
            _render_comsol_recipe_expander(cat_design, "cat_1d")


# ===========================================================================
# MODO 1.5: 1D Designer (DSL + IA + verificador)
# ===========================================================================
elif MODE == "1D Designer (IA)":
    col_left, col_right = st.columns([1, 1.4], gap="medium")

    with col_left:
        st.markdown("### 🤖 Generar con IA (1D)")
        tab_text, tab_img = st.tabs(["Descripción texto", "Imagen / esquema"])

        with tab_text:
            text_desc = st.text_area(
                "Describe el sistema cuántico 1D",
                placeholder=(
                    "Ej: Pozo cuántico finito GaAs de 30 nm con profundidad 250 meV.\n"
                    "Ej: Doble pozo gaussiano simétrico, separación 30 nm, sigma 5 nm.\n"
                    "Ej: Heteroestructura GaAs/AlGaAs con campo eléctrico de 1 mV/nm."
                ),
                height=130, key="text_1d_designer",
            )
            if st.button("🚀 Lanzar pipeline IA 1D (texto)",
                          disabled=not st.session_state.api_key_set,
                          key="btn_pipe_text_1d", type="primary"):
                if not text_desc.strip():
                    st.warning("Escribe una descripción.")
                else:
                    _remember_agent_text(text_desc)
                    _run_pipeline_text(text_desc)

        with tab_img:
            uploaded = st.file_uploader("Esquema 1D del potencial",
                                          type=["png","jpg","jpeg"],
                                          key="img_1d_uploader")
            extra_ctx = st.text_input("Contexto adicional",
                                        placeholder="Ej: esquema heterojuntura, escala 100nm",
                                        key="ctx_1d")
            if st.button("🚀 Lanzar pipeline IA 1D (imagen)",
                          disabled=not st.session_state.api_key_set,
                          key="btn_pipe_img_1d", type="primary"):
                if uploaded is None:
                    st.warning("Sube una imagen.")
                else:
                    img_bytes = uploaded.read()
                    mime = "image/png" if uploaded.name.lower().endswith("png") else "image/jpeg"
                    _remember_agent_image(img_bytes, mime, uploaded.name)
                    _remember_agent_text(extra_ctx)
                    _run_pipeline_image(img_bytes, mime, extra_ctx)

        if not st.session_state.api_key_set:
            st.caption("⚠ Configura la API key en el sidebar.")

        st.markdown("### Material y dominio")
        mat_key = st.selectbox("Semiconductor", list_materials(),
                                index=list_materials().index(
                                    st.session_state.design_1d.get("material","GaAs")),
                                format_func=lambda k:f"{k}  (m*={MATERIALS[k].m_eff} mₑ)",
                                key="mat_designer_1d")
        st.session_state.design_1d["material"] = mat_key
        st.session_state.current_material = mat_key
        mat = MATERIALS[mat_key]

        L = st.slider("Dominio L (nm)", 40.0, 500.0,
                       float(st.session_state.design_1d.get("domain",{}).get("L",120)), 5.0,
                       key="domain_L_1d")
        N = st.select_slider("Resolución N", [256,512,1024,2048],
                              st.session_state.design_1d.get("domain",{}).get("N",1024),
                              key="domain_N_1d")
        st.session_state.design_1d["domain"] = {"L": L, "N": N}
        st.session_state.design_1d["dim"] = 1

        st.markdown("### 🧩 Pieces del Design (1D)")
        _render_pieces_editor()

        st.button("▶ Correr solver Schrödinger 1D", type="primary",
                   key="btn_solve_designer_1d", on_click=_run_solver_designer)
        _render_agent_harness()

    with col_right:
        x_nm = np.linspace(-L/2, L/2, N)
        try:
            V_eV = evaluate_design_1d(st.session_state.design_1d, x_nm)
        except Exception as e:
            st.error(f"Error evaluando Design 1D: {e}")
            V_eV = None

        if V_eV is not None:
            # Auto-clip para visualización (ignorar paredes infinitas)
            V_finite = V_eV[np.abs(V_eV) < 100]
            if len(V_finite) > 0:
                v_max = float(np.percentile(V_finite, 99) * 1000 + 30)
                v_min = float(np.min(V_finite) * 1000 - 30)
            else:
                v_min, v_max = -300.0, 100.0

            res_1d = (st.session_state.solver_result
                       if (st.session_state.solver_result is not None
                           and not hasattr(st.session_state.solver_result, "grid_size"))
                       else None)
            fig = _plot_textbook_1d(V_eV, x_nm, result=res_1d, V_clip=(v_min, v_max))
            st.plotly_chart(fig, use_container_width=True, key="textbook_1d_designer")

        if st.session_state.pipeline_result:
            _render_pipeline_trace(st.session_state.pipeline_result)

        res = st.session_state.solver_result
        if res is not None and not hasattr(res, "grid_size"):
            st.markdown("### Eigenvalores")
            cols_e = st.columns(min(len(res.energies_meV), 4))
            for i, (col, E) in enumerate(zip(cols_e, res.energies_meV)):
                col.metric(f"E{i}", f"{E:.2f} meV")
            if len(res.energies_meV) > 4:
                with st.expander("Ver todos los eigenvalores"):
                    for i, E in enumerate(res.energies_meV):
                        st.write(f"E{i} = {E:.4f} meV")

            st.markdown("### Exportar")
            d1, d2, d3, d4 = st.columns(4)
            with d1:
                st.download_button("📄 CSV", to_csv(res),
                                    "eigenvalores_1d.csv", "text/csv")
            with d2:
                st.download_button("🔢 NumPy", to_npz(res),
                                    "wavefunctions_1d.npz", "application/octet-stream")
            with d3:
                expr = design_to_matlab_expr_1d(st.session_state.design_1d)
                st.download_button("🔧 COMSOL .m",
                                    to_comsol_m_1d(res, "design_1d", {},
                                                    mat_key, mat.m_eff, expr),
                                    "comsol_1d.m", "text/plain")
            with d4:
                _render_mph_export(st.session_state.design_1d, mat_key, mat, "design_1d")
            _render_comsol_recipe_expander(st.session_state.design_1d, "design_1d")


# ===========================================================================
# MODO 2: 2D Catálogo (igual que antes)
# ===========================================================================
elif MODE == "2D Catálogo":
    col_left, col_right = st.columns([1, 1.4], gap="medium")
    pot_keys = list_potentials()
    pot_labels = {k: POTENTIALS[k].label for k in pot_keys}

    with col_left:
        st.markdown("### 1️⃣ Potencial 2D (catálogo)")
        cur = st.session_state.current_pot_2d
        if cur not in pot_keys: cur = pot_keys[0]
        pot_choice = st.selectbox("Tipo", pot_keys,
                                   format_func=lambda k: pot_labels[k],
                                   index=pot_keys.index(cur))
        if pot_choice != st.session_state.current_pot_2d:
            st.session_state.current_pot_2d = pot_choice
            st.session_state.current_params_2d = dict(POTENTIALS[pot_choice].params)
        st.caption(POTENTIALS[pot_choice].description)

        st.markdown("### 2️⃣ Material")
        mat_key = st.selectbox("Semiconductor", list_materials(),
                                index=list_materials().index(st.session_state.current_material),
                                format_func=lambda k:f"{k}  (m*={MATERIALS[k].m_eff} mₑ)")
        st.session_state.current_material = mat_key
        mat = MATERIALS[mat_key]

        st.markdown("### 3️⃣ Parámetros")
        pdef = POTENTIALS[st.session_state.current_pot_2d]
        updated = {}
        for pname, default in pdef.params.items():
            lo, hi, step = pdef.param_ranges[pname]
            unit = pdef.param_units.get(pname, "")
            cur = float(np.clip(
                st.session_state.current_params_2d.get(pname, default), lo, hi))
            updated[pname] = st.slider(
                f"{pname} [{unit}]", float(lo), float(hi), cur, float(step),
                key=f"slider_2d_{pname}",
            )
        st.session_state.current_params_2d = updated

        run_btn = st.button("▶ Correr solver Schrödinger 2D", type="primary")

    with col_right:
        N = st.session_state.grid_N_2d
        L = st.session_state.grid_L_2d
        x_nm, y_nm, X, Y = make_grid(L, N)
        V_eV = evaluate(st.session_state.current_pot_2d, X, Y,
                         st.session_state.current_params_2d)
        st.plotly_chart(_plot_potential_2d(V_eV, x_nm, y_nm),
                         use_container_width=True, key="pot_2d_cat")

        if run_btn:
            with st.spinner("Resolviendo..."):
                try:
                    res = solve(V_eV, x_nm, y_nm, mat.m_eff, st.session_state.n_states)
                    st.session_state.solver_result = res
                except Exception as e:
                    st.error(f"Error solver: {e}")

        res = st.session_state.solver_result
        if res is not None and hasattr(res, "grid_size"):
            st.markdown("### Eigenvalores")
            cols_e = st.columns(min(len(res.energies_meV), 4))
            for i, (col, E) in enumerate(zip(cols_e, res.energies_meV)):
                col.metric(f"E{i}", f"{E:.2f} meV")
            st.plotly_chart(_plot_wavefunctions_2d(res, n_show=4),
                             use_container_width=True, key="wf_2d_cat")
            st.markdown("### Exportar")
            d1,d2,d3,d4 = st.columns(4)
            with d1: st.download_button("📄 CSV", to_csv(res),
                                          "eigenvalores_2d.csv", "text/csv")
            with d2: st.download_button("🔢 NumPy", to_npz(res),
                                          "wavefunctions_2d.npz", "application/octet-stream")
            with d3: st.download_button("🔧 COMSOL .m",
                                          to_comsol_m(res, st.session_state.current_pot_2d,
                                                       st.session_state.current_params_2d,
                                                       mat_key, mat.m_eff, "V_manual"),
                                          "comsol_2d.m", "text/plain")
            with d4:
                cat_design = preset_to_design(st.session_state.current_pot_2d,
                                              st.session_state.current_params_2d, dim=2)
                cat_design["domain"] = {"L": st.session_state.grid_L_2d, "N": st.session_state.grid_N_2d}
                _render_mph_export(cat_design, mat_key, mat, "cat_2d")
            _render_comsol_recipe_expander(cat_design, "cat_2d")


# ===========================================================================
# MODO 3: 2D Designer (DSL + IA + verificador)
# ===========================================================================
else:
    col_left, col_right = st.columns([1, 1.4], gap="medium")

    with col_left:
        st.markdown("### 🤖 Generar con IA")
        tab_text, tab_img = st.tabs(["Descripción texto", "Imagen AFM/SEM"])

        with tab_text:
            text_desc = st.text_area(
                "Describe el sistema cuántico",
                placeholder=("Ej: Anillo cuántico GaAs de radio 40 nm "
                             "con donador en el centro y campo eléctrico de 1 mV/nm en x."),
                height=120,
            )
            if st.button("🚀 Lanzar pipeline IA (texto)",
                          disabled=not st.session_state.api_key_set,
                          key="btn_pipe_text", type="primary"):
                if not text_desc.strip():
                    st.warning("Escribe una descripción.")
                else:
                    _remember_agent_text(text_desc)
                    _run_pipeline_text(text_desc)

        with tab_img:
            uploaded = st.file_uploader("Imagen", type=["png","jpg","jpeg","tif","tiff"])
            extra_ctx = st.text_input("Contexto (opcional)",
                                       placeholder="Ej: AFM, escala 200 nm, InAs")
            if st.button("🚀 Lanzar pipeline IA (imagen)",
                          disabled=not st.session_state.api_key_set,
                          key="btn_pipe_img", type="primary"):
                if uploaded is None:
                    st.warning("Sube una imagen.")
                else:
                    img_bytes = uploaded.read()
                    mime = "image/png" if uploaded.name.lower().endswith("png") else "image/jpeg"
                    if uploaded.name.lower().endswith(("tif", "tiff")):
                        mime = "image/tiff"
                    _remember_agent_image(img_bytes, mime, uploaded.name)
                    _remember_agent_text(extra_ctx)
                    _run_pipeline_image(img_bytes, mime, extra_ctx)

        if not st.session_state.api_key_set:
            st.caption("⚠ Configura la API key en el sidebar.")

        # --- Material + dominio ---
        st.markdown("### Material y dominio")
        mat_key = st.selectbox("Semiconductor", list_materials(),
                                index=list_materials().index(
                                    st.session_state.design.get("material","GaAs")),
                                format_func=lambda k:f"{k}  (m*={MATERIALS[k].m_eff} mₑ)",
                                key="mat_designer")
        st.session_state.design["material"] = mat_key
        st.session_state.current_material = mat_key
        mat = MATERIALS[mat_key]

        L = st.slider("Dominio L (nm)", 50.0, 600.0,
                       float(st.session_state.design.get("domain",{}).get("L",200)), 10.0,
                       key="domain_L")
        N = st.select_slider("Resolución N", [48,64,96,128,192,256],
                              st.session_state.design.get("domain",{}).get("N",96),
                              key="domain_N")
        st.session_state.design["domain"] = {"L": L, "N": N}
        st.session_state.design["dim"] = 2

        # --- Editor de pieces ---
        st.markdown("### 🧩 Pieces del Design")
        _render_pieces_editor()

        st.button("▶ Correr solver Schrödinger 2D", type="primary", key="btn_solve_designer",
                   on_click=_run_solver_designer)
        _render_agent_harness()

    with col_right:
        # Visualización: render del Design en vivo + render IA + resultados
        x_nm = np.linspace(-L/2, L/2, N)
        y_nm = np.linspace(-L/2, L/2, N)
        X, Y = np.meshgrid(x_nm, y_nm)
        try:
            V_eV = evaluate_design(st.session_state.design, X, Y)
            st.plotly_chart(_plot_potential_2d_heatmap(V_eV, x_nm, y_nm),
                             use_container_width=True, key="design_heatmap")
        except Exception as e:
            st.error(f"Error evaluando Design: {e}")
            V_eV = None

        # Render 3D opcional
        with st.expander("Ver vista 3D del potencial"):
            if V_eV is not None:
                st.plotly_chart(_plot_potential_2d(V_eV, x_nm, y_nm,
                                                    title="V(x,y) en 3D"),
                                 use_container_width=True, key="design_3d")

        # --- Trace de IA (si hay pipeline_result) ---
        if st.session_state.pipeline_result:
            _render_pipeline_trace(st.session_state.pipeline_result)

        # --- Resultados solver ---
        res = st.session_state.solver_result
        if res is not None and hasattr(res, "grid_size"):
            st.markdown("### Eigenvalores")
            cols_e = st.columns(min(len(res.energies_meV), 4))
            for i, (col, E) in enumerate(zip(cols_e, res.energies_meV)):
                col.metric(f"E{i}", f"{E:.2f} meV")
            st.plotly_chart(_plot_wavefunctions_2d(res, n_show=4),
                             use_container_width=True, key="wf_designer")

            st.markdown("### Exportar")
            d1,d2,d3,d4 = st.columns(4)
            with d1: st.download_button("📄 CSV", to_csv(res),
                                          "eigenvalores.csv", "text/csv")
            with d2: st.download_button("🔢 NumPy", to_npz(res),
                                          "wavefunctions.npz", "application/octet-stream")
            with d3:
                expr = design_to_matlab_expr(st.session_state.design)
                st.download_button("🔧 COMSOL .m",
                                    to_comsol_m(res, "design",
                                                 {}, mat_key, mat.m_eff, expr),
                                    "comsol_design.m", "text/plain")
            with d4:
                _render_mph_export(st.session_state.design, mat_key, mat, "design_2d")
            _render_comsol_recipe_expander(st.session_state.design, "design_2d")
