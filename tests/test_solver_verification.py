from __future__ import annotations

import json

import pytest

from qpot import session, verification
from qpot.schema import design_hash


def _barrier_ring() -> dict:
    return {
        "schema_version": "1.0", "dim": 2, "material": "GaAs",
        "domain": {"L": 80.0, "N": 56},
        "parameters": {
            "Rin": {"value": 8, "unit": "nm", "dtype": "int", "kind": "length", "role": "radio interno"},
            "Rout": {"value": 24, "unit": "nm", "dtype": "int", "kind": "length", "role": "radio externo"},
            "Vb": {"value": 0.228, "unit": "eV", "dtype": "float", "kind": "energy", "role": "barrera"},
        },
        "pieces": [{
            "op": "where", "label": "anillo",
            "region": {"op": "intersection", "regions": [
                {"op": "disk", "args": {"center": [0, 0], "radius": "Rout"}},
                {"op": "complement", "region": {"op": "disk", "args": {
                    "center": [0, 0], "radius": "Rin"}}},
            ]},
            "inner": {"op": "constant", "args": {"value": 0}},
            "outer": {"op": "constant", "args": {"value": "Vb"}},
        }],
    }


def test_bound_states_use_exterior_escape_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    _, summary = session.solve_design(_barrier_ring(), n_states=3)
    assert summary["escape_threshold_meV"] == 228.0
    assert summary["n_bound_states"] == 3
    assert summary["eigensolver_residual_ok"]
    assert summary["max_normalization_error"] < 1e-8
    assert summary["orthogonality_error"] < 1e-8


def test_verify_requires_explicit_target_match(tmp_path, monkeypatch):
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    design = _barrier_ring()
    session.save_design(design)
    report = verification.verify_design(design, n_states=3)
    assert report["design_valid"]
    assert report["solver_valid"]
    assert report["target_match"]["ok"] is False
    assert report["ready_to_export"] is False
    assert report["analytic_benchmark"]["applicable"] is False
    assert (tmp_path / "verification.json").exists()


def test_agent_visual_assessment_can_satisfy_target(tmp_path, monkeypatch):
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    design = _barrier_ring()
    session.save_design(design)
    (tmp_path / "agent_assessment.json").write_text(json.dumps({
        "render_inspected": True, "score": 9, "matches": ["anillo"],
        "mismatches": [], "suggestions": [], "design_hash": design_hash(design),
    }))
    report = verification.verify_design(design, n_states=3)
    assert report["target_match"]["ok"] is True
    assert report["ready_to_export"] is True


def test_stale_agent_assessment_does_not_approve_modified_design(tmp_path, monkeypatch):
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    design = _barrier_ring()
    stale_hash = design_hash(design)
    design["parameters"]["Rout"]["value"] = 26
    session.save_design(design)
    (tmp_path / "agent_assessment.json").write_text(json.dumps({
        "render_inspected": True, "score": 10, "design_hash": stale_hash,
    }))
    report = verification.verify_design(design, n_states=3)
    assert report["target_match"]["ok"] is False


def test_2d_solver_preserves_degenerate_disk_states_and_reports_backend(tmp_path, monkeypatch):
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    design = {
        "schema_version": "1.0", "dim": 2, "material": "GaAs",
        "domain": {"L": 80.0, "N": 64},
        "parameters": {},
        "pieces": [{
            "op": "where", "label": "disco",
            "region": {"op": "disk", "args": {"center": [0, 0], "radius": 22}},
            "inner": {"op": "constant", "args": {"value": -0.2}},
            "outer": {"op": "constant", "args": {"value": 0}},
        }],
    }
    _, summary = session.solve_design(design, n_states=6)
    energies = summary["energies_meV"]
    assert energies[1] == pytest.approx(energies[2], abs=1e-5)
    assert summary["backend"] == "scipy-arpack-cpu"
    assert summary["requested_states"] == 6
    assert summary["computed_states"] > summary["requested_states"]
