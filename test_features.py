"""
test_features — regresión de core.features y core.image_analysis (sin API, sin COMSOL).

Protege el extractor de features cuantitativas y la heurística de visión clásica contra
regresiones del solver/render. Corre con pytest o directo: `python test_features.py`.
"""

from __future__ import annotations

import numpy as np

from core import features, image_analysis
from qpot import session


def _field(preset: str, dim: int) -> dict:
    design = session.preset_design(preset, dim)
    return session.evaluate_potential(design)


def test_double_well_1d():
    f = features.extract_features(_field("double_well", 1))
    assert f["n_wells"] == 2, f
    assert f["n_barriers"] == 1, f
    assert f["symmetric"] is True, f
    assert len(f["well_positions_nm"]) == 2


def test_finite_well_1d():
    f = features.extract_features(_field("finite_well", 1))
    assert f["n_wells"] == 1, f
    assert f["symmetric"] is True, f


def test_morse_1d():
    # La pared repulsiva de Morse infla v_max; el clip robusto debe seguir viendo el pozo.
    f = features.extract_features(_field("morse", 1))
    assert f["n_wells"] == 1, f
    assert 400 < f["well_depths_meV"][0] < 600, f


def test_barrier_1d():
    # Potencial sin pozo: la barrera positiva no debe desaparecer con el clip.
    f = features.extract_features(_field("barrier", 1))
    assert f["n_wells"] == 0, f
    assert f["n_barriers"] == 1, f


def test_quantum_ring_2d():
    f = features.extract_features(_field("quantum_ring", 2))
    assert f["ring_like"] is True, f
    assert f["radial_symmetry"] is True, f


def test_quantum_dot_2d():
    f = features.extract_features(_field("quantum_dot", 2))
    assert f["ring_like"] is False, f
    assert f["radial_symmetry"] is True, f
    assert f["n_wells"] >= 1, f


def test_analytic_benchmark_harmonic():
    # Oscilador armónico: E1−E0 debe reproducir ħω casi exacto (<2%).
    design = session.preset_design("harmonic", 1)
    field = session.evaluate_potential(design)
    _, summary = session.solve_design(design, n_states=3)
    b = features.harmonic_benchmark(field, summary["m_eff"], summary["energies_meV"])
    assert b["applicable"] and b["model"] == "harmonic_bottom", b
    assert b["deviation_pct"] < 2.0, b


def test_analytic_benchmark_infinite_well():
    # Caja infinita: espaciado E1−E0 = 3·E1_box (<5%).
    design = session.preset_design("infinite_well", 1)
    field = session.evaluate_potential(design)
    _, summary = session.solve_design(design, n_states=3)
    b = features.harmonic_benchmark(field, summary["m_eff"], summary["energies_meV"])
    assert b["applicable"] and b["model"] == "particle_in_box", b
    assert b["deviation_pct"] < 5.0, b


def test_solver_morse_converges():
    # Regresión: la pared de Morse antes tumbaba ARPACK (shift-invert fallback).
    design = session.preset_design("morse", 1)
    _, summary = session.solve_design(design, n_states=4)
    assert summary["convergence_ok"], summary
    E = summary["energies_meV"]
    assert E[0] < -400, E  # fondo del pozo Morse (De=0.5 eV)


def _synthetic(kind: str, path: str) -> str:
    import matplotlib.image as mpimg
    N = 200
    yy, xx = np.mgrid[-1:1:N * 1j, -1:1:N * 1j]
    r = np.sqrt(xx ** 2 + yy ** 2)
    if kind == "ring":
        img = 1 - np.exp(-((r - 0.5) ** 2) / 0.02)
    elif kind == "dot":
        img = 1 - np.exp(-(r ** 2) / 0.05)
    else:  # two dots
        img = 1 - (np.exp(-((xx - 0.4) ** 2 + yy ** 2) / 0.02)
                   + np.exp(-((xx + 0.4) ** 2 + yy ** 2) / 0.02))
    mpimg.imsave(path, img, cmap="gray")
    return path


def test_analyze_image_ring(tmp_path=None):
    import tempfile
    p = _synthetic("ring", tempfile.mktemp(suffix=".png"))
    assert image_analysis.analyze_image(p)["suggested_preset"] == "quantum_ring"


def test_analyze_image_dot():
    import tempfile
    p = _synthetic("dot", tempfile.mktemp(suffix=".png"))
    assert image_analysis.analyze_image(p)["suggested_preset"] == "quantum_dot"


def test_analyze_image_two():
    import tempfile
    p = _synthetic("two", tempfile.mktemp(suffix=".png"))
    assert image_analysis.analyze_image(p)["suggested_preset"] == "double_dot"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
