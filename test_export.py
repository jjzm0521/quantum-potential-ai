import sys
import os

# Asegurar que el path incluya el directorio raíz
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.exporter_mph import export_mph
from core.materials import get_material

# Diseño no trivial: Pozo super-elíptico rotado con impureza Coulomb fuera de centro
design_complex = {
    "dim": 2,
    "material": "GaAs",
    "domain": {"L": 200.0, "N": 128},
    "pieces": [
        {
            "label": "pozo super-elíptico rotado",
            "op": "mask",
            "region": {
                "op": "super_ellipse",
                "args": {
                    "center": [0.0, 0.0],
                    "a": 30.0,
                    "b": 20.0,
                    "n": 3.0,
                    "angle_deg": 45.0
                }
            },
            "value": -0.25
        },
        {
            "label": "impureza Coulomb desplazada",
            "op": "coulomb",
            "args": {
                "center": [5.0, 5.0],
                "charge": 1.0,
                "eps_r": 12.9,
                "regularization": 1.5
            }
        }
    ]
}

material = get_material("GaAs")
n_states = 6
output_file = "test_complex_well.mph"

print("Iniciando exportación a COMSOL...")
try:
    path = export_mph(design_complex, "GaAs", material.m_eff, n_states, output_file)
    print(f"Éxito: Archivo COMSOL generado en {os.path.abspath(path)}")
except Exception as e:
    print(f"Error durante la generación: {e}")
