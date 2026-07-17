"""
Exporter MPh — genera un archivo .mph directamente desde Python.

Requiere:
  - COMSOL Multiphysics instalado en la máquina
  - pip install MPh (envoltorio Python sobre la Java API)
  - Java (lo trae COMSOL)

Si MPh no está disponible, este módulo falla LIMPIO con una excepción
informativa. La app principal usa try/except para deshabilitar el botón.
"""

from __future__ import annotations
import os
import json
import warnings
from pathlib import Path
from datetime import datetime

# Configurar JAVA_HOME para usar el JRE de COMSOL (Java 11) si no está definido.
# Previene el error "Java version too old. Java 9 or later is required" debido a Java 8 del sistema.
if not os.environ.get("JAVA_HOME"):
    comsol_base = r"C:\Program Files\COMSOL"
    if os.path.exists(comsol_base):
        for folder in os.listdir(comsol_base):
            jre_path = os.path.join(comsol_base, folder, "Multiphysics", "java", "win64", "jre")
            if os.path.exists(jre_path):
                os.environ["JAVA_HOME"] = jre_path
                break

from .composer import design_to_matlab_expr
from .harnex import validate_for_comsol_export, ComsolExportError


def _attach_qpot_metadata(model, design: dict, material_name: str, m_eff: float) -> str:
    """Embed traceability metadata in fields readable through the COMSOL Java API."""
    from qpot.schema import design_hash

    revision_hash = design_hash(design)
    metadata = {
        "generator": "Quantum Potential AI",
        "generator_version": "1.0.0",
        "schema_version": str(design.get("schema_version", "legacy")),
        "design_hash": revision_hash,
        "material": material_name,
        "effective_mass_me": float(m_eff),
        "parameters": design.get("parameters", {}),
    }
    model.java.label(f"Quantum Potential AI 1.0 [{revision_hash[:12]}]")
    model.java.comments("QPOT_METADATA_JSON=" + json.dumps(metadata, sort_keys=True))
    return revision_hash


def _configure_effective_mass(physics) -> None:
    """Configure the electron effective mass using COMSOL 5.6 property names."""
    feature = physics.java.feature("meff1")
    feature.set("meffe_psi_src", "userdef")
    feature.set("meffe_psi", "m_eff*me_const")


def _spectral_shift_eV(design: dict) -> float:
    """Place COMSOL's shift below the spectrum so it returns the lowest bound states."""
    import numpy as np
    from .composer import resolve_params, evaluate_design, evaluate_design_1d
    from .solver import make_grid

    resolved = resolve_params(design)
    dim = int(resolved.get("dim", 2))
    domain = resolved.get("domain") or {}
    length = float(domain.get("L", 120.0 if dim == 1 else 200.0))
    if dim == 1:
        count = min(max(int(domain.get("N", 256)), 128), 1024)
        x = np.linspace(-length / 2, length / 2, count)
        minimum = float(np.min(evaluate_design_1d(resolved, x)))
    else:
        count = min(max(int(domain.get("N", 96)), 64), 160)
        _x, _y, X, Y = make_grid(length, count)
        minimum = float(np.min(evaluate_design(resolved, X, Y)))
    return minimum


def mph_available() -> tuple[bool, str]:
    """Devuelve (disponible, mensaje). Útil para mostrar al usuario."""
    try:
        import mph  # noqa: F401
    except ImportError:
        return (False,
                "MPh no instalado. Ejecuta: pip install MPh")
    return (True, "MPh disponible.")


def export_mph(
    design: dict,
    material_name: str,
    m_eff: float,
    n_states: int,
    output_path: str | Path,
) -> Path:
    """
    Construye un modelo COMSOL desde el Design y lo guarda como .mph.

    Args:
      design: dict (esquema del composer)
      material_name: "GaAs" / "InAs" / ...
      m_eff: masa efectiva en m_e
      n_states: nº de eigenvalores a calcular
      output_path: ruta destino del .mph

    Returns:
      Path al archivo guardado
    """
    # Puerta de validación pre-export: bloquea Designs que el modelo COMSOL
    # no podría construir o que producirían resultados sin sentido.
    issues = validate_for_comsol_export(design, material_name, m_eff, n_states)
    if issues:
        raise ComsolExportError(issues)

    try:
        import mph
    except ImportError as e:
        raise RuntimeError(
            "MPh no está instalado. Instala con: pip install MPh\n"
            f"Detalle: {e}"
        )

    dim = design.get("dim", 2)
    L_nm = design.get("domain", {}).get("L", 200.0 if dim == 2 else 120.0)
    L_m  = L_nm * 1e-9

    if dim == 1:
        from .composer import design_to_matlab_expr_1d
        expr_str = design_to_matlab_expr_1d(design)
    else:
        from .composer import design_to_matlab_expr
        expr_str = design_to_matlab_expr(design)

    # Iniciar cliente COMSOL
    client = mph.start()
    model = client.create("QuantumPotentialAI")
    _attach_qpot_metadata(model, design, material_name, m_eff)

    # Parámetros físicos
    model.parameter("hbar",   "1.054571817e-34[J*s]")
    model.parameter("m_e",    "9.10938e-31[kg]")
    model.parameter("m_eff",  str(m_eff))
    model.parameter("m_star", "m_eff*m_e")
    model.parameter("L",      f"{L_m}[m]")
    from .comsol_export import collect_parameters
    for name, expr, _desc in collect_parameters(design):
        model.parameter(name, expr)

    # Geometría
    geom = model.create("geometries/geom1", dim)
    if dim == 1:
        interval = geom.create("Interval", name="i1")
        interval.property("p1", "-L/2")
        interval.property("p2", "L/2")
    else:
        rect = geom.create("Rectangle", name="r1")
        rect.property("lx",     "L")
        rect.property("ly",     "L")
        rect.property("base",   "center")
    geom.run()

    # Función analítica V en eV (coordenadas en metros)
    func = model.create("functions/V_pot", "Analytic")
    func.property("funcname", "V_pot")
    func.property("expr",     expr_str)
    if dim == 1:
        func.property("args",     "x")
        func.property("argunit",  "m")
        func.property("plotargs", [["x", "-L/2", "L/2"]])
    else:
        func.property("args",     "x,y")
        func.property("argunit",  "m,m")
        func.property("plotargs", [["x", "-L/2", "L/2"], ["y", "-L/2", "L/2"]])
    func.property("fununit",  "eV")

    if dim == 2:
        # Física: interfaz dedicada de Schrödinger con energía potencial del electrón.
        # COMSOL 5.6 expects the dependent-field matrix as the third argument. Passing
        # the geometry tag here selects the wrong overload and creates CoefficientFormPDE.
        phys = model.create("physics/schr", "SchrodingerEquation", geom.tag(), [["psi"]])
        _configure_effective_mass(phys)
        phys.java.feature("ve1").active(False)
        ve = phys.create("ElectronPotentialEnergy", name="ve_afm")
        ve.java.selection().all()
        ve.java.set("Ve_src", "userdef")
        ve.java.set("Ve", expr_str)
    else:
        phys = model.create("physics/schr", "SchrodingerEquation", geom.tag(), [["psi"]])
        _configure_effective_mass(phys)
        ve = phys.java.feature("ve1")
        ve.set("Ve_src", "userdef")
        ve.set("Ve", expr_str)

    # Malla
    mesh = model.create("meshes/mesh1", geom.name())
    # Use the finest automatic preset: narrow smooth features must satisfy the
    # same 1% Python–COMSOL criterion as broad Gaussian wells.
    mesh.java.autoMeshSize(1)
    mesh.run()

    # Estudio eigenvalor
    study = model.create("studies/std1")
    eig = study.create("Eigenvalue", name="eig")
    eig.property("neigsactive", True)
    eig.property("neigs", n_states)
    eig.java.set("shift", repr(_spectral_shift_eV(design)))

    # Guardar (no correr — el profe lo corre desde COMSOL)
    out = Path(output_path)
    model.save(str(out))
    try:
        client.disconnect()
    except Exception as exc:
        warnings.warn(f"El .mph se guardó, pero MPh no pudo desconectarse: {exc}", RuntimeWarning)

    return out


def export_mph_or_fallback(
    design: dict,
    material_name: str,
    m_eff: float,
    n_states: int,
    output_path: str | Path,
) -> tuple[Path | None, str]:
    """
    Intenta exportar a .mph. Si falla, retorna (None, mensaje_error).
    Si tiene éxito, retorna (path, mensaje_ok).
    """
    try:
        path = export_mph(design, material_name, m_eff, n_states, output_path)
        return path, f"Modelo COMSOL guardado en {path}"
    except Exception as e:
        return None, f"No se pudo generar .mph: {e}"


# ===========================================================================
# .mph NATIVO POR GEOMETRÍA + interfaz Schrödinger (schr)  — 2D
# ===========================================================================

def _mask_points(mask, x, y, min_pixels: int = 4):
    """One deep interior point per resolved connected component.

    Sub-grid one-to-three-pixel islands occur at cusps/tangent curves because the
    raster classifier and exact COMSOL geometry use different boundary tolerances.
    They are not physical domains and would create overlapping Ball selections.
    """
    import numpy as np
    from scipy import ndimage
    pts: list[tuple[float, float]] = []
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return pts
    labels, ncomp = ndimage.label(mask)
    for c in range(1, ncomp + 1):
        comp = labels == c
        if int(np.count_nonzero(comp)) < min_pixels:
            continue
        dist = ndimage.distance_transform_edt(comp)
        iy, ix = np.unravel_index(int(np.argmax(dist)), dist.shape)
        pts.append((float(x[ix]), float(y[iy])))
    return pts


def _interior_points(region: dict, L_nm: float, N: int = 220):
    """Puntos interiores (uno por componente conexa) de una región, en nm."""
    import numpy as np
    from .composer import _evaluate_region
    from .solver import make_grid
    x, y, X, Y = make_grid(L_nm, N)
    mask = np.asarray(_evaluate_region(region, X, Y), dtype=bool)
    return _mask_points(mask, x, y)


def _region_inner_outer_points(region: dict, L_nm: float, N: int = 220):
    """Puntos interiores de la región (inner) y de su complemento (outer).

    Garantiza un reparto **disjunto y completo** del dominio: cada zona se selecciona
    por puntos interiores reales, sin solapes y cubriéndolo todo.
    """
    import numpy as np
    from .composer import _evaluate_region
    from .solver import make_grid
    x, y, X, Y = make_grid(L_nm, N)
    mask = np.asarray(_evaluate_region(region, X, Y), dtype=bool)
    return _mask_points(mask, x, y), _mask_points(~mask, x, y)


def _partition_potential_points(assignments: list[dict], design: dict, L_nm: float,
                                N: int = 360) -> list[dict]:
    """Return a complete, exclusive potential partition for COMSOL domains.

    Boolean geometry can split one logical region (especially its complement) into
    several COMSOL domains. We classify the cells induced by every atomic boundary,
    keep a deep point in each connected cell, and group the cells by final ``Ve``.
    """
    import json as _json
    import numpy as np
    from .composer import _evaluate_region
    from .solver import make_grid
    from . import comsol_export as cx

    resolved_regions = [_resolve_region(a["region"], design) for a in assignments]
    atomic_regions: list[dict] = []
    seen: set[str] = set()
    for region in resolved_regions:
        for atom in cx._iter_atomic_regions(region):
            key = _json.dumps(atom, sort_keys=True)
            if key not in seen:
                seen.add(key)
                atomic_regions.append(atom)
    if len(atomic_regions) > 62:
        raise ValueError("La partición COMSOL excede 62 regiones atómicas.")

    x, y, X, Y = make_grid(L_nm, N)
    assignment_masks = [np.asarray(_evaluate_region(region, X, Y), dtype=bool)
                        for region in resolved_regions]
    signatures = np.zeros(X.shape, dtype=np.uint64)
    for index, atom in enumerate(atomic_regions):
        atom_mask = np.asarray(_evaluate_region(atom, X, Y), dtype=bool)
        signatures |= atom_mask.astype(np.uint64) << np.uint64(index)

    grouped: dict[str, list[tuple[float, float]]] = {}
    for signature in np.unique(signatures):
        cell = signatures == signature
        points = _mask_points(cell, x, y)
        if not points:
            continue
        iy, ix = np.argwhere(cell)[0]
        active = [index for index, mask in enumerate(assignment_masks) if mask[iy, ix]]
        if len(active) > 1:
            raise ValueError("La partición contiene potenciales regionales solapados.")
        expression = assignments[active[0]]["value"] if active else assignments[0]["base"]
        grouped.setdefault(expression, []).extend(points)

    if not grouped:
        raise ValueError("No se pudo materializar la partición de potencial COMSOL.")
    return [{"expression": expression, "points": points}
            for expression, points in grouped.items()]


def export_mph_geometry(
    design: dict,
    material_name: str,
    m_eff: float,
    n_states: int,
    output_path: str | Path,
) -> Path:
    """Construye un .mph NATIVO con geometría por regiones (Curvas Paramétricas +
    primitivas) y la interfaz **Ecuación de Schrödinger** (Masa efectiva + Energía
    potencial de electrón por dominio) + estudio de Valor propio. Sólo 2D.

    El potencial por dominio se asigna seleccionando cada región por un punto interior
    (Ball selection), robusto a la numeración de dominios de COMSOL.
    """
    from .composer import resolve_params, _evaluate_region  # noqa: F401
    from . import comsol_export as cx

    resolved = resolve_params(design)
    issues = validate_for_comsol_export(
        resolved,
        material_name,
        m_eff,
        n_states,
        require_analytic_expression=False,
    )
    issues += cx.exportability_issues(design)
    if issues:
        raise ComsolExportError(issues)
    if int(design.get("dim", 2)) != 2:
        raise ValueError("export_mph_geometry es sólo para 2D.")

    try:
        import mph
        from jpype import JInt
    except ImportError as e:
        raise RuntimeError("MPh no está instalado. Instala con: pip install MPh") from e

    L_nm = float((design.get("domain") or {}).get("L", 200.0))
    assignments, analytic = cx.domain_potentials(design)

    client = mph.start()
    model = client.create("QuantumPotentialGeom")
    _attach_qpot_metadata(model, design, material_name, m_eff)

    # --- Parámetros globales (nombres conservados → barridos en COMSOL) ---
    model.parameter("m_eff", str(m_eff))
    model.parameter("Ldom", f"{L_nm}[nm]")
    for name, expr, _desc in cx.collect_parameters(design):
        model.parameter(name, expr)

    # --- Geometría 2D: Cuadrado dominio + curvas/primitivas de cada región ---
    geom = model.create("geometries/geom1", 2)
    sq = geom.create("Square", name="dom")
    sq.property("size", "Ldom")
    sq.property("base", "center")

    # regiones atómicas únicas
    atoms: list[tuple[str, dict]] = []
    seen = set()
    import json as _json
    for a in assignments:
        for atom in cx._iter_atomic_regions(a["region"]):
            key = _json.dumps(atom, sort_keys=True)
            if key not in seen:
                seen.add(key)
                atoms.append((f"reg{len(atoms)+1}", atom))

    for tag, atom in atoms:
        op = atom.get("op")
        args = atom.get("args", {})
        if op == "super_ellipse":
            xs, ys = cx.superellipse_polygon_coordinates(args)
            poly = geom.create("Polygon", name=tag)
            poly.property("x", xs)
            poly.property("y", ys)
        elif op in ("epicycloid", "hypocycloid"):
            xs, ys = cx.cycloid_polygon_coordinates(op, args)
            poly = geom.create("Polygon", name=tag)
            poly.property("x", xs)
            poly.property("y", ys)
        elif op == "disk":
            cxx, cyy = cx._center_tokens(args.get("center", [0.0, 0.0]))
            c = geom.create("Circle", name=tag)
            c.property("r", cx._tok(args.get("radius", 10.0)))
            c.property("pos", [cxx, cyy])
            c.property("base", "center")
        elif op == "annulus":
            cxx, cyy = cx._center_tokens(args.get("center", [0.0, 0.0]))
            for suffix, radius in (("o", args.get("r_outer", 10.0)),
                                   ("i", args.get("r_inner", 5.0))):
                circle = geom.create("Circle", name=f"{tag}_{suffix}")
                circle.property("r", cx._tok(radius))
                circle.property("pos", [cxx, cyy])
                circle.property("base", "center")
        elif op == "ellipse":
            cxx, cyy = cx._center_tokens(args.get("center", [0.0, 0.0]))
            e = geom.create("Ellipse", name=tag)
            e.property("semiaxes", [cx._tok(args.get("a", 15.0)), cx._tok(args.get("b", 10.0))])
            e.property("pos", [cxx, cyy])
            e.property("base", "center")
            e.property("rot", cx._tok(args.get("angle_deg", 0.0), unit="deg"))
        elif op == "rectangle":
            cxx, cyy = cx._center_tokens(args.get("center", [0.0, 0.0]))
            r = geom.create("Rectangle", name=tag)
            r.property("size", [cx._tok(args.get("Lx", 20.0)), cx._tok(args.get("Ly", 20.0))])
            r.property("pos", [cxx, cyy])
            r.property("base", "center")
            r.property("rot", cx._tok(args.get("angle_deg", 0.0), unit="deg"))
        elif op == "polygon":
            vertices = args.get("vertices", atom.get("vertices", []))
            if len(vertices) < 3:
                raise ValueError(f"Polígono '{tag}' necesita al menos 3 vértices.")
            poly = geom.create("Polygon", name=tag)
            poly.property("x", [cx._tok(v[0]) for v in vertices])
            poly.property("y", [cx._tok(v[1]) for v in vertices])
        else:
            raise ValueError(f"Región '{op}' no soportada por el export .mph estricto.")
    geom.run()

    # --- Física: Ecuación de Schrödinger ---
    phys = model.create("physics/schr", "SchrodingerEquation", geom.tag(), [["psi"]])
    _configure_effective_mass(phys)

    # Deshabilitar el nodo de Energía potencial por DEFECTO de la interfaz (su Ve por
    # defecto es armónico y se aplica a todos los dominios → contamina). Lo reemplazamos
    # por nodos explícitos y disjuntos.
    phys.java.feature("ve1").active(False)

    def _selection_from_points(pts, key):
        nodes = []
        for j, (px, py) in enumerate(pts, 1):
            b = model.create(f"selections/{key}_{j}", "Ball")
            b.java.set("entitydim", JInt(2))
            b.java.set("posx", f"{px}[nm]")
            b.java.set("posy", f"{py}[nm]")
            b.java.set("r", "0.5[nm]")
            b.java.set("condition", "intersects")
            nodes.append(b)
        if not nodes:
            raise ValueError(f"La selección '{key}' no encontró ningún dominio interior.")
        if len(nodes) == 1:
            return nodes[0].java.tag()
        u = model.create(f"selections/{key}_u", "Union")
        u.java.set("entitydim", JInt(2))
        u.java.set("input", [bn.java.tag() for bn in nodes])
        return u.java.tag()

    def _add_potential(name, sel_tag, ve_expr):
        ve = phys.create("ElectronPotentialEnergy", name=name)
        if sel_tag is not None:
            ve.java.selection().named(sel_tag)
        else:
            ve.java.selection().all()
        ve.java.set("Ve_src", "userdef")
        ve.java.set("Ve", ve_expr)

    if assignments:
        # Every domain induced by every atomic boundary receives exactly one final Ve.
        # This includes holes and disconnected exterior pieces in boolean/where regions.
        zones = _partition_potential_points(assignments, design, L_nm)
        for index, zone in enumerate(zones, 1):
            selection = _selection_from_points(zone["points"], f"sel_zone{index}")
            _add_potential(f"ve_zone_{index}", selection, zone["expression"])
    else:
        # Sin regiones (perfil analítico tipo raw_expr): V como expresión en todo el dominio.
        from .composer import design_to_matlab_expr
        expr = f"({design_to_matlab_expr(resolve_params(design))})[eV]"
        _add_potential("ve_all", None, expr)

    # --- Malla ---
    mesh = model.create("meshes/mesh1", geom.name())
    # The central-peak/annular-trench demo contains a narrow 4.5 nm feature;
    # preset 2 left one excited state at 1.28% error.  Preset 1 resolves that
    # scale while the sparse Python solver remains the independent reference.
    mesh.java.autoMeshSize(1)
    mesh.run()

    # --- Estudio de valor propio ---
    study = model.create("studies/std1")
    eig = study.create("Eigenvalue", name="eigv")
    eig.property("neigs", n_states)
    eig.java.set("shift", repr(_spectral_shift_eV(design)))

    out = Path(output_path)
    model.save(str(out))
    try:
        client.disconnect()
    except Exception as exc:
        # En modo stand-alone disconnect() puede no aplicar; el archivo ya fue guardado,
        # pero el incidente queda visible para no ocultar excepciones.
        warnings.warn(f"El .mph se guardó, pero MPh no pudo desconectarse: {exc}", RuntimeWarning)
    return out


def _resolve_region(region: dict, design: dict) -> dict:
    """Resuelve las referencias de parámetros dentro de una región suelta."""
    from .composer import resolve_params
    wrapped = {"parameters": design.get("parameters", {}),
               "pieces": [{"op": "mask", "region": region, "value": 0}]}
    return resolve_params(wrapped)["pieces"][0]["region"]


def export_mph_geometry_or_fallback(
    design: dict,
    material_name: str,
    m_eff: float,
    n_states: int,
    output_path: str | Path,
) -> tuple[Path | None, str]:
    try:
        path = export_mph_geometry(design, material_name, m_eff, n_states, output_path)
        return path, f"Modelo COMSOL (geometría + Schrödinger) guardado en {path}"
    except Exception as e:
        return None, f"No se pudo generar .mph por geometría: {e}"
