"""
Propiedades físicas de semiconductores comunes.
Fuente: Vurgaftman et al., J. Appl. Phys. 89, 5815 (2001)
"""

from dataclasses import dataclass

# Constantes físicas (SI)
HBAR = 1.054571817e-34   # J·s
M_E  = 9.10938e-31        # kg
EV   = 1.60218e-19        # J por eV


@dataclass
class Material:
    name: str
    m_eff: float      # masa efectiva en unidades de m_e
    E_gap: float      # band gap en eV (referencia)
    epsilon_r: float  # constante dieléctrica relativa

    @property
    def m_kg(self) -> float:
        return self.m_eff * M_E


MATERIALS: dict[str, Material] = {
    "GaAs":  Material("GaAs",  m_eff=0.067, E_gap=1.424, epsilon_r=12.9),
    "InAs":  Material("InAs",  m_eff=0.023, E_gap=0.354, epsilon_r=15.2),
    "InGaAs":Material("InGaAs",m_eff=0.041, E_gap=0.750, epsilon_r=13.9),
    "Si":    Material("Si",    m_eff=0.191, E_gap=1.120, epsilon_r=11.7),
    "GaN":   Material("GaN",   m_eff=0.200, E_gap=3.400, epsilon_r=9.0),
    "libre": Material("libre", m_eff=1.000, E_gap=0.000, epsilon_r=1.0),
}


def get_material(name: str) -> Material:
    key = name.strip()
    if key not in MATERIALS:
        raise ValueError(f"Material '{key}' no conocido. Opciones: {list(MATERIALS)}")
    return MATERIALS[key]


def list_materials() -> list[str]:
    return list(MATERIALS.keys())
