"""
Quantum Potential - visualizador local sin API.

La app comparte la misma sesion que el CLI `python -m qpot`: lee y escribe
`session/design.json`. El agente externo puede construir el potencial, y el
usuario puede verlo, ajustar parametros, resolver Schrodinger y exportar.

Uso:
    python -m streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core.materials import list_materials
from core.potentials import POTENTIALS
from core.potentials_1d import POTENTIALS_1D
from qpot import render, session, projects, verification
from qpot.schema import normalize_parameter, set_parameter


st.set_page_config(
    page_title="Quantum Potential - Visualizador",
    page_icon="Q",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2rem; }
      .stButton > button { width: 100%; }
      .qpot-stage {
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 8px;
        padding: 0.65rem 0.8rem;
        background: rgba(255,255,255,0.035);
        min-height: 4.3rem;
      }
      .qpot-stage strong { display:block; margin-bottom:0.2rem; }
      .qpot-muted { color: rgba(250,250,250,0.72); font-size: 0.88rem; }
      div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 0.65rem 0.75rem;
      }
      /* Ocultar el chrome de Streamlit para un look limpio (sin Deploy/menu/footer). */
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }
      [data-testid="stToolbar"] { display: none; }
      [data-testid="stDecoration"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_design_or_none() -> dict[str, Any] | None:
    try:
        return session.load_design()
    except FileNotFoundError:
        return None


def save_and_rerun(design: dict[str, Any]) -> None:
    session.save_design(design)
    st.rerun()


def plot_potential(field: dict[str, Any], mode: str) -> go.Figure:
    if field["dim"] == 1:
        v_mev = field["V_eV"] * 1000.0
        fig = go.Figure(
            go.Scatter(
                x=field["x_nm"],
                y=v_mev,
                mode="lines",
                line=dict(color="#4A90D9", width=2.5),
                name="V(x)",
            )
        )
        finite = v_mev[np.isfinite(v_mev)]
        if finite.size:
            lo = float(np.percentile(finite, 1))
            hi = float(np.percentile(finite, 99))
            pad = max(10.0, 0.1 * (hi - lo))
            fig.update_yaxes(range=[lo - pad, hi + pad])
        fig.update_layout(
            height=460,
            margin=dict(l=8, r=8, t=34, b=8),
            template="plotly_white",
            title="Potencial V(x)",
            xaxis_title="x (nm)",
            yaxis_title="V (meV)",
        )
        return fig

    x = field["x_nm"]
    y = field["y_nm"]
    v_mev = field["V_eV"] * 1000.0
    cmin, cmax = render._clip_range(v_mev)
    v_plot = np.clip(v_mev, cmin, cmax) if cmin is not None else v_mev

    if mode == "Vista superior":
        fig = go.Figure(
            go.Heatmap(
                x=x,
                y=y,
                z=v_plot,
                colorscale="Viridis",
                colorbar=dict(title="V (meV)"),
            )
        )
        fig.update_yaxes(scaleanchor="x", scaleratio=1)
        title = "Potencial V(x,y) - vista superior"
    else:
        fig = go.Figure(
            go.Surface(
                x=x,
                y=y,
                z=v_plot,
                colorscale="Viridis",
                cmin=cmin,
                cmax=cmax,
                colorbar=dict(title="V (meV)"),
            )
        )
        fig.update_layout(
            scene=dict(
                xaxis_title="x (nm)",
                yaxis_title="y (nm)",
                zaxis_title="V (meV)",
            )
        )
        title = "Potencial V(x,y) - superficie 3D"

    fig.update_layout(
        height=560,
        margin=dict(l=8, r=8, t=36, b=8),
        template="plotly_white",
        title=title,
    )
    return fig


def plot_wavefunctions(result: Any, dim: int, state_index: int = 0) -> go.Figure:
    if dim == 1:
        fig = go.Figure()
        v_mev = result.V_eV * 1000.0
        fig.add_trace(
            go.Scatter(
                x=result.x_nm,
                y=v_mev,
                mode="lines",
                line=dict(color="#222", width=1.8),
                name="V(x)",
            )
        )
        energies = result.energies_meV
        n_show = min(5, len(energies))
        if n_show:
            spread = float(np.max(energies[:n_show]) - np.min(energies[:n_show]))
            amp = max(12.0, spread / max(1, n_show))
        else:
            amp = 20.0
        for i in range(n_show):
            psi = result.wavefunctions[i]
            psi_scaled = psi / (np.max(np.abs(psi)) + 1e-12) * amp + energies[i]
            fig.add_trace(
                go.Scatter(
                    x=result.x_nm,
                    y=psi_scaled,
                    mode="lines",
                    name=f"E{i} = {energies[i]:.2f} meV",
                )
            )
        fig.update_layout(
            height=470,
            margin=dict(l=8, r=8, t=34, b=8),
            template="plotly_white",
            title="Estados ligados 1D",
            xaxis_title="x (nm)",
            yaxis_title="E (meV) / psi",
        )
        return fig

    idx = int(np.clip(state_index, 0, len(result.energies_meV) - 1))
    fig = go.Figure(
        go.Heatmap(
            x=result.x_nm,
            y=result.y_nm,
            z=result.wavefunctions[idx],
            colorscale="Magma",
            colorbar=dict(title="|psi|^2"),
        )
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(
        height=470,
        margin=dict(l=8, r=8, t=34, b=8),
        template="plotly_white",
        title=f"Densidad |psi|^2 - estado {idx}, E = {result.energies_meV[idx]:.2f} meV",
        xaxis_title="x (nm)",
        yaxis_title="y (nm)",
    )
    return fig


def coerce_param_value(value: Any, key: str) -> Any:
    if isinstance(value, bool):
        return st.checkbox(key, value=value, key=f"param_{key}_{id(value)}")
    if isinstance(value, int) and not isinstance(value, bool):
        return int(st.number_input(key, value=int(value), step=1, key=f"param_{key}_{id(value)}"))
    if isinstance(value, float):
        return float(st.number_input(key, value=float(value), format="%.6f", key=f"param_{key}_{id(value)}"))
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, (int, float)) for v in value)
    ):
        c1, c2 = st.columns(2)
        return [
            float(c1.number_input(f"{key}[0]", value=float(value[0]), key=f"param_{key}_0_{id(value)}")),
            float(c2.number_input(f"{key}[1]", value=float(value[1]), key=f"param_{key}_1_{id(value)}")),
        ]
    return st.text_input(key, value=json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value))


def edit_args(args: dict[str, Any], prefix: str) -> None:
    for key in list(args.keys()):
        widget_key = f"{prefix}_{key}"
        val = args[key]
        if isinstance(val, bool):
            args[key] = st.checkbox(key, value=val, key=widget_key)
        elif isinstance(val, int) and not isinstance(val, bool):
            args[key] = int(st.number_input(key, value=int(val), step=1, key=widget_key))
        elif isinstance(val, float):
            args[key] = float(st.number_input(key, value=float(val), format="%.6f", key=widget_key))
        elif (
            isinstance(val, (list, tuple))
            and len(val) == 2
            and all(isinstance(v, (int, float)) for v in val)
        ):
            c1, c2 = st.columns(2)
            args[key] = [
                float(c1.number_input(f"{key}[0]", value=float(val[0]), key=f"{widget_key}_0")),
                float(c2.number_input(f"{key}[1]", value=float(val[1]), key=f"{widget_key}_1")),
            ]
        else:
            raw = st.text_input(key, value=json.dumps(val, ensure_ascii=False), key=widget_key)
            try:
                args[key] = json.loads(raw)
            except json.JSONDecodeError:
                args[key] = raw


def edit_number_or_reference(label: str, value: Any, key: str) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(st.number_input(label, value=float(value), format="%.6f", key=key))

    raw = st.text_input(
        label,
        value=json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value),
        help="Puedes escribir un número en eV o el nombre de un parámetro, por ejemplo Vring.",
        key=key,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def edit_piece(piece: dict[str, Any], index: int) -> None:
    piece["label"] = st.text_input("Etiqueta", value=piece.get("label", piece.get("op", "")), key=f"label_{index}")
    piece["enabled"] = st.checkbox("Habilitada", value=piece.get("enabled", True), key=f"enabled_{index}")
    if "value" in piece:
        piece["value"] = edit_number_or_reference("Valor (eV o parametro)", piece.get("value", 0.0), key=f"value_{index}")
    if isinstance(piece.get("args"), dict):
        st.caption("Parametros")
        edit_args(piece["args"], prefix=f"piece_{index}")
    if isinstance(piece.get("region"), dict):
        st.caption(f"Region: {piece['region'].get('op')}")
        piece["region"].setdefault("args", {})
        edit_args(piece["region"]["args"], prefix=f"region_{index}")


def preset_catalog(dim: int) -> dict[str, Any]:
    return POTENTIALS_1D if dim == 1 else POTENTIALS


def preset_form(dim: int) -> tuple[str, dict[str, Any]]:
    catalog = preset_catalog(dim)
    name = st.selectbox("Preset", list(catalog.keys()))
    params: dict[str, Any] = {}
    defaults = catalog[name].params
    for key, default in defaults.items():
        if isinstance(default, int) and not isinstance(default, bool):
            params[key] = int(st.number_input(key, value=int(default), step=1, key=f"preset_{dim}_{name}_{key}"))
        elif isinstance(default, float):
            params[key] = float(st.number_input(key, value=float(default), format="%.6f", key=f"preset_{dim}_{name}_{key}"))
        else:
            raw = st.text_input(key, value=json.dumps(default, ensure_ascii=False), key=f"preset_{dim}_{name}_{key}")
            try:
                params[key] = json.loads(raw)
            except json.JSONDecodeError:
                params[key] = raw
    return name, params


def render_sidebar(design: dict[str, Any] | None) -> bool:
    with st.sidebar:
        st.header("Proyecto")
        available = projects.list_projects()
        if available:
            names = [p["slug"] for p in available]
            active = projects.active_slug()
            selected = st.selectbox("Proyecto activo", names,
                                    index=names.index(active) if active in names else 0)
            if selected != active:
                projects.set_active(selected)
                st.rerun()
        with st.expander("Nuevo proyecto"):
            project_name = st.text_input("Nombre", key="new_project_name")
            project_dim = st.radio("Dimensión inicial", [1, 2], horizontal=True,
                                   key="new_project_dim")
            if st.button("Crear proyecto", disabled=not bool(project_name.strip())):
                projects.create_project(project_name, dim=project_dim, material="GaAs", activate=True)
                st.rerun()
        st.caption("Carpeta compartida por la app, el CLI y el agente.")
        st.code(str(session.session_dir()), language=None)
        live = st.toggle("Vista en vivo", help="Relee design.json cada 2 segundos.")

        st.divider()
        st.subheader("Pedido al agente")
        st.caption("Usa esto como puente tipo Text2CAD: describes el potencial y el agente modifica la misma sesion.")
        goal = st.text_area(
            "Objetivo",
            value="Construye un anillo cuantico de GaAs, radio 45 nm y profundidad 300 meV.",
            height=90,
        )
        if design is not None:
            dim = int(design.get("dim", 2))
            material = design.get("material", "GaAs")
        else:
            dim = 2
            material = "GaAs"
        st.code(
            "Pidele al agente:\n"
            f"{goal}\n\n"
            "Luego verifica con:\n"
            f"python -m qpot verify --n-states 6\n\n"
            "La app se actualiza desde el proyecto activo.",
            language="text",
        )
        with st.expander("Objetivo verificable"):
            target_path = session.artifact("target.json")
            try:
                target_data = json.loads(target_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                target_data = {"description": "", "features": {}, "tolerances": {}}
            target_description = st.text_area("Descripción del objetivo",
                                              value=target_data.get("description", ""),
                                              key="target_description")
            target_features = st.text_area("Features esperadas (JSON)",
                                           value=json.dumps(target_data.get("features", {}), ensure_ascii=False),
                                           key="target_features")
            target_tolerances = st.text_area("Tolerancias (JSON)",
                                             value=json.dumps(target_data.get("tolerances", {}), ensure_ascii=False),
                                             key="target_tolerances")
            if st.button("Guardar objetivo"):
                try:
                    projects._atomic_json(target_path, {
                        "description": target_description,
                        "features": json.loads(target_features),
                        "tolerances": json.loads(target_tolerances),
                    })
                    st.success("Objetivo guardado.")
                except json.JSONDecodeError as exc:
                    st.error(f"JSON inválido: {exc}")

        st.divider()
        st.subheader("Crear o reemplazar")
        new_dim = st.radio("Dimension", [1, 2], horizontal=True)
        new_material = st.selectbox("Material", list_materials())
        c1, c2 = st.columns(2)
        new_l = c1.number_input("L (nm)", value=float(session.default_domain(new_dim)["L"]), min_value=1.0)
        new_n = int(c2.number_input("N", value=int(session.default_domain(new_dim)["N"]), min_value=16, step=16))

        if st.button("Nueva sesion vacia"):
            session.clear_session()
            save_and_rerun(session.new_design(dim=new_dim, material=new_material, L=new_l, N=new_n))

        with st.expander("Cargar preset"):
            preset_name, preset_params = preset_form(new_dim)
            if st.button("Usar preset"):
                new_design = session.preset_design(preset_name, dim=new_dim, params=preset_params)
                new_design["material"] = new_material
                new_design["domain"] = {"L": float(new_l), "N": int(new_n)}
                session.clear_session()
                save_and_rerun(new_design)

        st.divider()
        st.subheader("Imagen fuente")
        uploaded = st.file_uploader("Registrar foto o esquema", type=["png", "jpg", "jpeg", "webp"])
        if uploaded is not None:
            suffix = Path(uploaded.name).suffix or ".png"
            target = session.artifact(f"_upload{suffix}")
            target.write_bytes(uploaded.getbuffer())
            session.register_source_image(target)
            target.unlink(missing_ok=True)
            st.success("Imagen registrada en la sesion.")
        src = session.source_image_path()
        if src is not None:
            st.image(str(src), caption="Imagen fuente actual", width="stretch")

        if design is not None:
            st.divider()
            st.subheader("Archivos")
            for name in ["design.json", "render.png", "wavefunctions.png", "result.json"]:
                p = session.artifact(name)
                if p.exists():
                    st.caption(str(p))
            history = sorted(session.artifact("history").glob("*.json"), reverse=True)
            st.caption(f"Revisiones guardadas: {len(history)}")
            for revision in history[:5]:
                st.caption(revision.name)
        return live


st.title("Quantum Potential - Mesa de diseno local")
st.caption(
    "Sin API paga. El agente construye el Design con qpot; aqui lo inspeccionas, "
    "mueves parametros, resuelves y exportas."
)

design = load_design_or_none()
live_mode = render_sidebar(design)

if design is None:
    st.info("No hay sesion activa. Crea una desde el panel lateral o pidele al agente que use `python -m qpot new`.")
    st.stop()


@st.fragment(run_every=2)
def live_view() -> None:
    current = load_design_or_none()
    if current is None:
        st.info("No hay sesion activa.")
        return
    field = session.evaluate_potential(current)
    c1, c2, c3 = st.columns(3)
    c1.metric("Dimension", f"{current.get('dim', 2)}D")
    c2.metric("Material", current.get("material", "GaAs"))
    c3.metric("Piezas", len(current.get("pieces", [])))
    mode = "Superficie 3D" if int(current.get("dim", 2)) == 2 else "Curva 1D"
    st.plotly_chart(plot_potential(field, mode), width="stretch")
    with st.expander("Design JSON"):
        st.code(json.dumps(current, ensure_ascii=False, indent=2), language="json")


if live_mode:
    st.info("Vista en vivo activada: la app sigue los cambios que haga el agente en session/design.json.")
    live_view()
    st.stop()

dim = int(design.get("dim", 2))
domain = design.setdefault("domain", session.default_domain(dim))

stage_cols = st.columns(4)
stage_cols[0].markdown(
    '<div class="qpot-stage"><strong>1. Objetivo</strong>'
    '<span class="qpot-muted">Describe el potencial al agente o carga un preset.</span></div>',
    unsafe_allow_html=True,
)
stage_cols[1].markdown(
    '<div class="qpot-stage"><strong>2. Design</strong>'
    '<span class="qpot-muted">session/design.json es la fuente de verdad.</span></div>',
    unsafe_allow_html=True,
)
stage_cols[2].markdown(
    '<div class="qpot-stage"><strong>3. Verificar</strong>'
    '<span class="qpot-muted">Render, validacion y solver local.</span></div>',
    unsafe_allow_html=True,
)
stage_cols[3].markdown(
    '<div class="qpot-stage"><strong>4. Exportar</strong>'
    '<span class="qpot-muted">CSV, NumPy, COMSOL .m/.mph o receta.</span></div>',
    unsafe_allow_html=True,
)

top = st.columns([1.2, 1, 1, 1])
materials = list_materials()
current_material = design.get("material", "GaAs")
design["material"] = top[0].selectbox(
    "Material",
    materials,
    index=materials.index(current_material) if current_material in materials else 0,
)
domain["L"] = float(top[1].number_input("Dominio L (nm)", value=float(domain.get("L", session.default_domain(dim)["L"])), min_value=1.0))
domain["N"] = int(top[2].number_input("Grilla N", value=int(domain.get("N", session.default_domain(dim)["N"])), min_value=16, step=16))
n_states = int(top[3].number_input("Estados", value=6, min_value=1, max_value=50))

left, right = st.columns([0.95, 1.35])

with left:
    st.subheader("Piezas y parametros")

    with st.expander("Parametros nombrados (geometria por parametros)",
                     expanded=bool(design.get("parameters"))):
        st.caption("Referéncialos por nombre en las piezas (p.ej. R = \"R2\"). "
                   "Un solo cambio de n / R1 / R2 mueve toda la geometría; quedan barribles en COMSOL.")
        params = design.setdefault("parameters", {})
        for pname in list(params.keys()):
            pc1, pc2 = st.columns([4, 1])
            record = normalize_parameter(pname, params[pname])
            cur = record["value"]
            label = f"{pname} ({record.get('unit') or 'adim.'})"
            if record["dtype"] == "int":
                value = int(pc1.number_input(label, value=int(cur), step=1,
                                             min_value=record.get("min"), max_value=record.get("max"),
                                             key=f"par_{pname}"))
            else:
                value = float(pc1.number_input(label, value=float(cur), format="%.6f",
                                               min_value=record.get("min"), max_value=record.get("max"),
                                               key=f"par_{pname}"))
            set_parameter(design, pname, value)
            if pc2.button("\U0001F5D1", key=f"delpar_{pname}", help="Eliminar parametro"):
                params.pop(pname, None)
                save_and_rerun(design)
        nc1, nc2, nc3 = st.columns([2, 2, 1])
        new_name = nc1.text_input("nombre", key="par_new_name", placeholder="nombre",
                                  label_visibility="collapsed")
        new_val = nc2.number_input("valor", key="par_new_val", value=0.0, format="%.6f",
                                   label_visibility="collapsed")
        if nc3.button("+", key="par_add", help="Agregar parametro") and new_name:
            set_parameter(design, new_name, new_val)
            save_and_rerun(design)

    pieces = design.setdefault("pieces", [])
    if not pieces:
        st.info("El potencial no tiene piezas. Carga un preset o pidele al agente que agregue piezas.")

    for i, piece in enumerate(list(pieces)):
        title = f"#{i} - {piece.get('label', piece.get('op'))} ({piece.get('op')})"
        with st.expander(title, expanded=len(pieces) <= 3):
            edit_piece(piece, i)
            c1, c2 = st.columns(2)
            if c1.button("Guardar pieza", key=f"save_piece_{i}"):
                save_and_rerun(design)
            if c2.button("Eliminar", key=f"remove_piece_{i}"):
                pieces.pop(i)
                save_and_rerun(design)

    with st.expander("Agregar pieza rapida"):
        if dim == 1:
            op = st.selectbox("Tipo", ["gaussian", "barrier", "step", "linear", "harmonic"], key="add_1d")
            raw_args = {
                "gaussian": {"center": 0.0, "amplitude": -0.2, "sigma": 8.0},
                "barrier": {"center": 0.0, "height": 0.2, "width": 5.0},
                "step": {"position": 0.0, "height": 0.2},
                "linear": {"slope": 0.001, "offset": 0.0},
                "harmonic": {"center": 0.0, "omega_eV": 0.0005},
            }[op]
        else:
            op = st.selectbox("Tipo", ["gaussian", "mexican_hat", "coulomb", "linear", "harmonic_2d"], key="add_2d")
            raw_args = {
                "gaussian": {"center": [0.0, 0.0], "amplitude": -0.2, "sigma": 15.0},
                "mexican_hat": {"center": [0.0, 0.0], "r0": 40.0, "depth": 0.3},
                "coulomb": {"center": [0.0, 0.0], "charge": 1.0, "eps_r": 12.9, "regularization": 1.5},
                "linear": {"slope": 0.001, "axis": "x", "offset": 0.0},
                "harmonic_2d": {"center": [0.0, 0.0], "omega_eV": 0.0002},
            }[op]
        label = st.text_input("Etiqueta nueva", value=op)
        st.caption("Edita despues los parametros finos en la lista de piezas.")
        if st.button("Agregar pieza"):
            pieces.append({"op": op, "label": label, "args": raw_args})
            save_and_rerun(design)

    if st.button("Guardar todos los cambios", type="primary"):
        save_and_rerun(design)

    with st.expander("Design JSON"):
        st.code(json.dumps(design, ensure_ascii=False, indent=2), language="json")

with right:
    st.subheader("Visualizacion")
    view_mode = "Curva 1D"
    if dim == 2:
        view_mode = st.radio("Modo", ["Superficie 3D", "Vista superior"], horizontal=True)
    try:
        field = session.evaluate_potential(design)
        rng = session._range_summary(field["V_eV"])
        metrics = st.columns(3)
        metrics[0].metric("V min", f"{rng['min'] * 1000:.2f} meV")
        metrics[1].metric("V max", f"{rng['max'] * 1000:.2f} meV")
        metrics[2].metric("Piezas", len(pieces))
        st.plotly_chart(plot_potential(field, view_mode), width="stretch")
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo evaluar el potencial: {exc}")

    issues = session.validation_issues(design)
    if issues:
        st.warning("Validacion:\n- " + "\n- ".join(issues))
    else:
        st.success("Validacion OK.")

    actions = st.columns(3)
    if actions[0].button("Verificar", type="primary"):
        session.save_design(design)
        with st.spinner("Validando diseño, solver, malla, dominio y COMSOL..."):
            report = verification.verify_design(design, n_states=n_states, persist=True)
        st.session_state["last_verification"] = report
        if report["ready_to_export"]:
            st.success("Verificación completa: listo para exportar.")
        elif report["solver_valid"]:
            st.warning("Solver válido; falta objetivo/evaluación visual o preparación COMSOL.")
        else:
            st.error("La verificación científica requiere correcciones.")

    if actions[1].button("Resolver"):
        session.save_design(design)
        with st.spinner("Resolviendo Schrodinger..."):
            result, summary = session.solve_design(design, n_states=n_states)
        st.session_state["last_result"] = result
        st.session_state["last_summary"] = summary

    if actions[2].button("Guardar PNG/HTML"):
        session.save_design(design)
        field = session.evaluate_potential(design)
        render.render_potential(field, session.artifact("render.png"))
        render.render_potential_html(field, session.artifact("potential.html"))
        st.success("Render y HTML actualizados en session/.")

    result = st.session_state.get("last_result")
    summary = st.session_state.get("last_summary")
    verified = st.session_state.get("last_verification")
    if verified:
        st.subheader("Estado de verificación")
        cols = st.columns(4)
        cols[0].metric("Design", "OK" if verified["design_valid"] else "Revisar")
        cols[1].metric("Solver", "OK" if verified["solver_valid"] else "Revisar")
        cols[2].metric("COMSOL", "OK" if verified["comsol_ready"] else "Bloqueado")
        cols[3].metric("Objetivo", "OK" if verified["target_match"]["ok"] else "Pendiente")
        s = verified.get("solver", {})
        if s.get("solver_completed"):
            st.caption(
                f"Malla: {'OK' if s.get('grid_convergence_ok') else 'revisar'} · "
                f"Dominio: {'OK' if s.get('domain_convergence_ok') else 'revisar'} · "
                f"Fuga de borde: {'OK' if s.get('boundary_leakage_ok') else 'revisar'} · "
                f"Estados ligados: {s.get('n_bound_states')} bajo {s.get('escape_threshold_meV')} meV"
            )
        wf = session.artifact("wavefunctions.png")
        if wf.exists():
            st.image(str(wf), caption="Funciones de onda verificadas", width="stretch")
    if result is not None and summary is not None:
        st.subheader("Solver")
        e_cols = st.columns(min(4, len(summary["energies_meV"])))
        for i, energy in enumerate(summary["energies_meV"][: len(e_cols)]):
            e_cols[i].metric(f"E{i}", f"{energy:.2f} meV")
        st.caption(
            f"Convergencia: {'OK' if summary['convergence_ok'] else 'revisar'} | "
            f"estados ligados: {summary['n_bound_states']}"
        )
        state_idx = 0
        if dim == 2 and len(summary["energies_meV"]) > 1:
            state_idx = st.slider("Estado a visualizar", 0, len(summary["energies_meV"]) - 1, 0)
        st.plotly_chart(plot_wavefunctions(result, dim, state_idx), width="stretch")

st.divider()
st.subheader("Exportar")
export_cols = st.columns(5)
formats = [("m", "Script COMSOL .m"), ("mph", "COMSOL .mph"), ("csv", "Eigenvalores CSV"), ("npz", "Ondas NumPy"), ("recipe", "Receta COMSOL")]
for col, (fmt, label) in zip(export_cols, formats):
    if col.button(label, key=f"export_{fmt}"):
        session.save_design(design)
        with st.spinner(f"Exportando {fmt}..."):
            path, message = session.export_design(design, fmt, n_states=n_states)
        if path:
            st.success(message)
        else:
            st.error(message)
