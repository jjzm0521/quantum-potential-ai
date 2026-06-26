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

    # Parámetros físicos
    model.parameter("hbar",   "1.054571817e-34[J*s]")
    model.parameter("m_e",    "9.10938e-31[kg]")
    model.parameter("eV",     "1.60218e-19[J]")
    model.parameter("m_eff",  str(m_eff))
    model.parameter("m_star", "m_eff*m_e")
    model.parameter("L",      f"{L_m}[m]")
    if dim == 2:
        try:
            from .comsol_export import collect_parameters
            for name, expr, _desc in collect_parameters(design):
                model.parameter(name, expr)
        except Exception:
            pass

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
        phys = model.create("physics/schr", "SchrodingerEquation", geom.name())
        try:
            phys.java.feature("meff1").set("meff", "m_eff")
        except Exception:
            pass
        try:
            phys.java.feature("ve1").active(False)
        except Exception:
            pass
        ve = phys.create("ElectronPotentialEnergy", name="ve_afm")
        ve.java.selection().all()
        ve.java.set("Ve_src", "userdef")
        ve.java.set("Ve", "V_pot(x,y)")
    else:
        # 1D conserva el camino PDE analítico legacy.
        phys = model.create("physics/c", "CoefficientFormPDE", geom.name())
        phys.java.field("dimensionless").fieldname(["psi"])
        cfeq = phys.java.feature("cfeq1")
        cfeq.set("c", "hbar^2/(2*m_star)")
        cfeq.set("a", "V_pot(x)*eV")
        cfeq.set("da", "1")
        diri = phys.create("DirichletBoundary", name="dir1")
        diri.select("all")
        diri.property("r", "0")

    # Malla
    mesh = model.create("meshes/mesh1", geom.name())
    mesh.java.autoMeshSize(3 if dim == 2 else 2)  # 3 = Normal (2D), 2 = Fine (1D)
    mesh.run()

    # Estudio eigenvalor
    study = model.create("studies/std1")
    eig = study.create("Eigenvalue", name="eig")
    eig.property("neigsactive", True)
    eig.property("neigs", n_states)

    # Guardar (no correr — el profe lo corre desde COMSOL)
    out = Path(output_path)
    model.save(str(out))
    try:
        client.disconnect()
    except Exception:
        pass

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

def _mask_points(mask, x, y):
    """Un punto interior 'profundo' (máx. distancia al borde) por componente conexa."""
    import numpy as np
    from scipy import ndimage
    pts: list[tuple[float, float]] = []
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return pts
    labels, ncomp = ndimage.label(mask)
    for c in range(1, ncomp + 1):
        comp = labels == c
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
    issues = validate_for_comsol_export(resolved, material_name, m_eff, n_states)
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
        if op in ("epicycloid", "hypocycloid", "super_ellipse", "rose"):
            xe, ye = cx._parametric_expr(op, args)
            pc = geom.create("ParametricCurve", name=tag)
            pc.property("parname", "s")
            pc.property("parmax", "2*pi")
            pc.property("coord", [xe, ye])
        elif op == "disk":
            cxx, cyy = cx._center_tokens(args.get("center", [0.0, 0.0]))
            c = geom.create("Circle", name=tag)
            c.property("r", cx._tok(args.get("radius", 10.0)))
            c.property("pos", [cxx, cyy])
            c.property("base", "center")
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
        # (otras regiones: se omiten de la geometría; el dominio base las cubre)
    geom.run()

    # --- Física: Ecuación de Schrödinger ---
    phys = model.create("physics/schr", "SchrodingerEquation", geom.name())
    try:
        phys.java.feature("meff1").set("meff", "m_eff")
    except Exception:
        pass  # nombre de propiedad puede variar según versión; masa por defecto si falla

    # Deshabilitar el nodo de Energía potencial por DEFECTO de la interfaz (su Ve por
    # defecto es armónico y se aplica a todos los dominios → contamina). Lo reemplazamos
    # por nodos explícitos y disjuntos.
    for dtag in ("ve1", "epe1", "pe1"):
        try:
            phys.java.feature(dtag).active(False)
        except Exception:
            pass

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
            return None
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

    if len(assignments) == 1:
        # Reparto DISJUNTO y COMPLETO: región (inner) + su complemento (outer).
        # Para la corona: inner = canal (dominio 2) = inner_value; outer = barreras
        # (dominios 1 y 3) = outer_value. Sin solapes, sin dejar dominios fuera.
        a = assignments[0]
        region = _resolve_region(a["region"], design)
        inner_pts, outer_pts = _region_inner_outer_points(region, L_nm)
        _add_potential("ve_inner", _selection_from_points(inner_pts, "sel_in"), a["value"])
        _add_potential("ve_outer", _selection_from_points(outer_pts, "sel_out"), a["base"])
    elif assignments:
        # Varias regiones: base en todo + overrides por región (COMSOL resuelve por
        # exclusividad: el nodo posterior se queda con sus dominios).
        _add_potential("ve_base", None, assignments[0]["base"])
        for k, a in enumerate(assignments, 1):
            pts = _interior_points(_resolve_region(a["region"], design), L_nm)
            _add_potential(f"ve_{k}", _selection_from_points(pts, f"sel{k}"), a["value"])
    else:
        # Sin regiones (perfil analítico tipo raw_expr): V como expresión en todo el dominio.
        from .composer import design_to_matlab_expr
        try:
            expr = f"({design_to_matlab_expr(resolve_params(design))})[eV]"
        except Exception:
            expr = "0[eV]"
        _add_potential("ve_all", None, expr)

    # --- Malla ---
    mesh = model.create("meshes/mesh1", geom.name())
    mesh.java.autoMeshSize(3)
    mesh.run()

    # --- Estudio de valor propio ---
    study = model.create("studies/std1")
    eig = study.create("Eigenvalue", name="eigv")
    eig.property("neigs", n_states)
    try:
        eig.java.set("eigref", "0.1")
    except Exception:
        pass

    out = Path(output_path)
    model.save(str(out))
    try:
        client.disconnect()
    except Exception:
        pass  # en modo stand-alone disconnect() puede no aplicar; el .mph ya se guardó
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
