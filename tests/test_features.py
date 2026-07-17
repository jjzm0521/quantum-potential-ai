from __future__ import annotations

from core import features
from qpot import session


def _field(name: str, dim: int):
    return session.evaluate_potential(session.preset_design(name, dim))


def test_classic_features():
    double = features.extract_features(_field("double_well", 1))
    assert double["n_wells"] == 2 and double["symmetric"]
    ring = features.extract_features(_field("quantum_ring", 2))
    assert ring["ring_like"] and ring["radial_symmetry"]


def test_analytic_benchmarks():
    for preset, model, limit in (("harmonic", "harmonic_bottom", 2.0),
                                 ("infinite_well", "particle_in_box", 5.0)):
        design = session.preset_design(preset, 1)
        field = session.evaluate_potential(design)
        _, summary = session.solve_design(design, 3)
        bench = features.harmonic_benchmark(field, summary["m_eff"], summary["energies_meV"])
        assert bench["applicable"] and bench["model"] == model
        assert bench["deviation_pct"] < limit

