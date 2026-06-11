import os
import mph
from pathlib import Path

# Configurar JAVA_HOME para usar el JRE de COMSOL
comsol_base = r"C:\Program Files\COMSOL"
if os.path.exists(comsol_base):
    for folder in os.listdir(comsol_base):
        jre_path = os.path.join(comsol_base, folder, "Multiphysics", "java", "win64", "jre")
        if os.path.exists(jre_path):
            os.environ["JAVA_HOME"] = jre_path
            break

# Iniciar cliente COMSOL
print("Iniciando cliente COMSOL...")
try:
    client = mph.start()
    model = client.create("QuantumPotentialParameterized")

    # Parámetros físicos estándar
    model.parameter("hbar",   "1.054571817e-34[J*s]")
    model.parameter("m_e",    "9.10938e-31[kg]")
    model.parameter("eV",     "1.60218e-19[J]")
    model.parameter("m_eff",  "0.067")  # GaAs
    model.parameter("m_star", "m_eff*m_e")
    model.parameter("L",      "200[nm]")

    # Parámetros personalizados solicitados por el usuario
    model.parameter("a",      "10[nm]")   # Radio de los pozos
    model.parameter("b",      "30[nm]")   # Distancia entre centros
    model.parameter("V0",     "-236[meV]") # Profundidad del pozo (negativo para pozo)

    # Geometría 2D
    dim = 2
    geom = model.create("geometries/geom1", dim)
    rect = geom.create("Rectangle", name="r1")
    rect.property("lx",     "L")
    rect.property("ly",     "L")
    rect.property("base",   "center")
    geom.run()

    # Función analítica V_pot en eV con parámetros a, b, V0
    # Usamos || para la disyunción lógica compatible con COMSOL
    expr_str = "V0 * ( (sqrt((x + b/2)^2 + y^2) <= a) || (sqrt((x - b/2)^2 + y^2) <= a) )"

    func = model.create("functions/V_pot", "Analytic")
    func.property("funcname", "V_pot")
    func.property("expr",     expr_str)
    func.property("args",     "x,y")
    func.property("argunit",  "m,m")
    func.property("plotargs", [["x", "-L/2", "L/2"], ["y", "-L/2", "L/2"]])
    func.property("fununit",  "eV")

    # Física: ecuación de Schrödinger
    phys = model.create("physics/c", "CoefficientFormPDE", geom.name())
    phys.java.field("dimensionless").fieldname(["psi"])

    # Configurar coeficientes
    cfeq = phys.java.feature("cfeq1")
    cfeq.set("c", "hbar^2/(2*m_star)")
    cfeq.set("a", "V_pot(x,y)*eV")
    cfeq.set("da", "1")

    # Dirichlet en bordes
    diri = phys.create("DirichletBoundary", name="dir1")
    diri.select("all")
    diri.property("r", "0")

    # Malla
    mesh = model.create("meshes/mesh1", geom.name())
    mesh.java.autoMeshSize(3)  # Normal
    mesh.run()

    # Estudio eigenvalor
    study = model.create("studies/std1")
    eig = study.create("Eigenvalue", name="eig")
    eig.property("neigsactive", True)
    eig.property("neigs", 6)

    # Guardar
    output_file = Path("test_parameterized.mph").resolve()
    model.save(str(output_file))
    client.disconnect()
    print(f"Éxito: Archivo COMSOL parametrizado generado en {output_file}")
except Exception as e:
    print(f"Error durante la generación: {e}")
