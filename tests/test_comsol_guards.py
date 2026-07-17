from __future__ import annotations

from core import comsol_export
from core.composer import design_to_matlab_expr_1d
from core.exporter_mph import _attach_qpot_metadata, _spectral_shift_eV
import pytest
from qpot import session
from qpot.schema import design_hash


def test_unsupported_geometry_is_explicitly_blocked():
    design = {
        "dim": 2, "domain": {"L": 100, "N": 64}, "material": "GaAs",
        "pieces": [{"op": "mask", "region": {"op": "half_plane", "args": {
            "axis": "x", "threshold": 0, "side": "positive"}}, "value": -0.1}],
    }
    issues = comsol_export.exportability_issues(design)
    assert issues and "half_plane" in " ".join(issues)


def test_annulus_has_strict_geometry_translation():
    design = {
        "dim": 2, "domain": {"L": 100, "N": 64}, "material": "GaAs",
        "pieces": [{"op": "mask", "region": {"op": "annulus", "args": {
            "center": [0, 0], "r_inner": 5, "r_outer": 20}}, "value": -0.1}],
    }
    assert comsol_export.exportability_issues(design) == []
    assert "Dos círculos" in comsol_export.design_to_comsol_recipe(design)


def test_mixed_domain_and_analytic_potentials_are_blocked():
    design = {
        "dim": 2, "domain": {"L": 100, "N": 64}, "material": "GaAs",
        "pieces": [
            {"op": "mask", "region": {"op": "disk", "args": {
                "center": [0, 0], "radius": 20}}, "value": -0.1},
            {"op": "linear", "args": {"slope": 0.001, "axis": "x", "offset": 0}},
        ],
    }
    assert any("mezcla" in issue for issue in comsol_export.exportability_issues(design))


def test_unsupported_analytic_primitive_never_becomes_zero_potential():
    design = {"dim": 1, "domain": {"L": 100, "N": 64}, "material": "GaAs",
              "pieces": [{"op": "invented_profile", "args": {}}]}
    issues = comsol_export.exportability_issues(design)
    assert issues and "invented_profile" in " ".join(issues)
    with pytest.raises(ValueError, match="invented_profile"):
        design_to_matlab_expr_1d(design)


def test_typed_parameters_keep_comsol_units_in_analytic_expression():
    design = {
        "dim": 1,
        "parameters": {
            "x0": {"value": 0, "unit": "nm", "dtype": "float", "kind": "length", "role": "center"},
            "sigma": {"value": 5, "unit": "nm", "dtype": "float", "kind": "length", "role": "width"},
        },
        "pieces": [{"op": "gaussian", "args": {
            "center": "x0", "sigma": "sigma", "amplitude": -0.2}}],
    }
    expr = design_to_matlab_expr_1d(design)
    assert "(x0)" in expr and "(sigma)" in expr
    assert "x0e-9" not in expr and "sigmae-9" not in expr


def test_mph_metadata_contains_revision_and_physics_context():
    class JavaModel:
        def label(self, value):
            self.model_label = value

        def comments(self, value):
            self.model_comments = value

    model = type("Model", (), {"java": JavaModel()})()
    design = {"schema_version": "1.0", "dim": 1, "parameters": {}, "pieces": []}
    revision = _attach_qpot_metadata(model, design, "GaAs", 0.067)
    assert revision[:12] in model.java.model_label
    assert '"material": "GaAs"' in model.java.model_comments
    assert '"effective_mass_me": 0.067' in model.java.model_comments


def test_comsol56_mass_uses_explicit_electron_mass_properties():
    from pathlib import Path

    source = Path("core/exporter_mph.py").read_text(encoding="utf-8")
    assert 'set("meffe_psi_src", "userdef")' in source
    assert 'set("meffe_psi", "m_eff*me_const")' in source
    assert '.set("meff",' not in source
    assert 'model.parameter("eV"' not in source


def test_comsol_spectral_shift_targets_negative_bound_states():
    design = {
        "dim": 1, "domain": {"L": 100, "N": 128},
        "pieces": [{"op": "mask", "region": {"op": "interval", "args": {
            "center": 0, "length": 30}}, "value": -0.3}],
    }
    assert _spectral_shift_eV(design) == pytest.approx(-0.3)


def test_analytic_comsol_potential_is_assigned_directly_without_double_unit_conversion():
    from pathlib import Path

    source = Path("core/exporter_mph.py").read_text(encoding="utf-8")
    assert 've.set("Ve", expr_str)' in source
    assert 've.java.set("Ve", expr_str)' in source
    assert 'set("Ve", "V_pot(' not in source


@pytest.mark.parametrize("region", [
    {"op": "disk", "args": {"center": [0, 0], "radius": 20}},
    {"op": "rectangle", "args": {"center": [0, 0], "Lx": 30, "Ly": 20}},
    {"op": "ellipse", "args": {"center": [0, 0], "a": 20, "b": 12}},
    {"op": "super_ellipse", "args": {"center": [0, 0], "a": 20, "b": 12, "n": 4}},
    {"op": "annulus", "args": {"center": [0, 0], "r_inner": 8, "r_outer": 20}},
    {"op": "intersection", "regions": [
        {"op": "epicycloid", "args": {"center": [0, 0], "R": 28, "n": 7}},
        {"op": "complement", "region": {"op": "hypocycloid", "args": {
            "center": [0, 0], "R": 12, "n": 7}}},
    ]},
])
def test_required_comsol_regions_have_recipe_and_no_static_blocker(region):
    design = {"dim": 2, "material": "GaAs", "domain": {"L": 100, "N": 64},
              "pieces": [{"op": "mask", "region": region, "value": -0.1}]}
    assert comsol_export.exportability_issues(design) == []
    recipe = comsol_export.design_to_comsol_recipe(design)
    assert "Schrödinger" in recipe and "Valor propio" in recipe


def test_two_disjoint_domains_are_exportable_but_overlap_is_not():
    def design(separation):
        return {"dim": 2, "material": "GaAs", "domain": {"L": 100, "N": 64},
                "pieces": [
                    {"op": "mask", "label": "a", "region": {"op": "disk", "args": {
                        "center": [-separation, 0], "radius": 10}}, "value": -0.1},
                    {"op": "mask", "label": "b", "region": {"op": "disk", "args": {
                        "center": [separation, 0], "radius": 10}}, "value": -0.2},
                ]}
    assert comsol_export.exportability_issues(design(20)) == []
    assert any("solapan" in issue for issue in comsol_export.exportability_issues(design(5)))


def test_mph_fallback_must_be_explicit(tmp_path, monkeypatch):
    design = {"dim": 2, "material": "GaAs", "domain": {"L": 80, "N": 48},
              "pieces": [{"op": "mask", "region": {"op": "disk", "args": {
                  "center": [0, 0], "radius": 20}}, "value": -0.1}]}
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(session, "export_mph_geometry_or_fallback",
                        lambda *args, **kwargs: (None, "MPh ausente"))
    (tmp_path / "verification.json").write_text(__import__("json").dumps({
        "design_hash": design_hash(design), "ready_to_export": True,
    }))
    path, message = session.export_design(design, "mph")
    assert path is None and "--allow-fallback" in message
    path, _ = session.export_design(design, "mph", allow_fallback=True)
    assert path and path.suffix == ".md" and path.exists()


def test_remote_certification_matrix_is_statically_exportable():
    from scripts.comsol56_certification_suite import mandatory_cases

    cases = mandatory_cases()
    assert len(cases) >= 10
    failures = {
        name: comsol_export.exportability_issues(design)
        for name, design in cases.items()
        if comsol_export.exportability_issues(design)
    }
    assert failures == {}


def test_comsol56_exporter_does_not_emit_unsupported_eigref_property():
    from pathlib import Path

    source = Path("core/exporter_mph.py").read_text(encoding="utf-8")
    assert 'set("eigref"' not in source
    assert 'model.create("physics/schr", "SchrodingerEquation", geom.tag(), [["psi"]])' in source
    assert 'model.create("physics/schr", "SchrodingerEquation", geom.name())' not in source
