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

    # Física: ecuación de Schrödinger vía CoefficientFormPDE
    phys = model.create("physics/c", "CoefficientFormPDE", geom.name())
    phys.java.field("dimensionless").fieldname(["psi"])

    # Configurar coeficientes
    cfeq = phys.java.feature("cfeq1")
    cfeq.set("c", "hbar^2/(2*m_star)")
    if dim == 1:
        cfeq.set("a", "V_pot(x)*eV")
    else:
        cfeq.set("a", "V_pot(x,y)*eV")
    cfeq.set("da", "1")

    # Dirichlet en bordes
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
    client.disconnect()

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
