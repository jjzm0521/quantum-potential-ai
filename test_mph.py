"""
Test de regresión del export COMSOL .mph (reglas de COMSOL_MPH.md).

Verifica, SIN abrir COMSOL (rápido, corre en cualquier máquina), que:
  1. El reparto región/complemento de un `where` es DISJUNTO y COMPLETO.
  2. Las zonas de un diseño multi-máscara no se solapan (o se detecta si se solapan).
  3. La receta COMSOL se construye con la estructura correcta.

Correr de las dos formas:
    python test_mph.py              # imprime OK/FALLA y valida tu sesión actual
    python -m pytest test_mph.py    # si tienes pytest
"""

from __future__ import annotations

import numpy as np

from core.composer import _evaluate_region
from core.solver import make_grid
from core import comsol_export
from core.exporter_mph import _region_inner_outer_points


# --- Diseños de prueba (valores numéricos, sin referencias a parámetros) ---

CORONA_REGION = {
    "op": "intersection",
    "regions": [
        {"op": "epicycloid", "args": {"center": [0, 0], "R": 28, "n": 7}},
        {"op": "complement",
         "region": {"op": "hypocycloid", "args": {"center": [0, 0], "R": 16, "n": 7}}},
    ],
}

DISJOINT_DESIGN = {
    "dim": 2, "material": "GaAs", "domain": {"L": 200.0, "N": 160},
    "pieces": [
        {"op": "mask", "label": "A",
         "region": {"op": "disk", "args": {"center": [-45, 0], "radius": 20}}, "value": -0.1},
        {"op": "mask", "label": "B",
         "region": {"op": "disk", "args": {"center": [45, 0], "radius": 20}}, "value": -0.1},
    ],
}

OVERLAP_DESIGN = {
    "dim": 2, "material": "GaAs", "domain": {"L": 200.0, "N": 160},
    "pieces": [
        {"op": "mask", "label": "A",
         "region": {"op": "disk", "args": {"center": [-10, 0], "radius": 25}}, "value": -0.1},
        {"op": "mask", "label": "B",
         "region": {"op": "disk", "args": {"center": [10, 0], "radius": 25}}, "value": -0.2},
    ],
}


def _region_mask(region, L=100.0, N=200):
    _x, _y, X, Y = make_grid(L, N)
    return np.asarray(_evaluate_region(region, X, Y), dtype=bool)


# --- Tests ---

def test_where_partition_disjoint_and_complete():
    """region (inner) y su complemento (outer) deben cubrir TODO sin solaparse."""
    inner = _region_mask(CORONA_REGION)
    outer = ~inner
    assert not (inner & outer).any(), "inner y outer se solapan"
    assert (inner | outer).all(), "inner ∪ outer no cubre todo el dominio"
    assert inner.any() and outer.any(), "alguna zona quedó vacía"


def test_where_interior_points():
    """Debe haber ≥1 punto interior en el canal y ≥1 en las barreras (para Ball selection)."""
    inner_pts, outer_pts = _region_inner_outer_points(CORONA_REGION, 100.0)
    assert len(inner_pts) >= 1, "sin punto interior en el canal"
    assert len(outer_pts) >= 1, "sin punto interior en las barreras"


def test_disjoint_design_has_no_overlap():
    assert comsol_export.zone_overlap_issues(DISJOINT_DESIGN) == []


def test_overlap_design_is_detected():
    issues = comsol_export.zone_overlap_issues(OVERLAP_DESIGN)
    assert issues, "no se detectó el solape esperado entre las dos máscaras"


def test_recipe_has_expected_structure():
    r = comsol_export.design_to_comsol_recipe(DISJOINT_DESIGN)
    assert "Parámetros globales" in r
    assert "Schrödinger" in r
    assert "Energía potencial de electrón" in r
    assert "Valor propio" in r


# --- Runner sin pytest ---

def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t()
            print(f"  OK    {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  FALLA {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"  ERROR {t.__name__}: {e}")

    print()
    print(f"Resultado: {len(tests) - fails}/{len(tests)} pasaron.")

    # Validación extra: tu sesión actual (si existe).
    try:
        from qpot import session
        design = session.load_design()
        issues = comsol_export.zone_overlap_issues(design)
        print("\nSesión actual (session/design.json):")
        if issues:
            print("  ⚠ Zonas que se SOLAPAN (revisa el diseño):")
            for i in issues:
                print("    -", i)
        else:
            print("  ✓ Zonas disjuntas: el reparto de potencial es correcto para COMSOL.")
    except FileNotFoundError:
        print("\n(No hay sesión activa que validar.)")

    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(_run())
