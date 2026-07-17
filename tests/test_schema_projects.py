from __future__ import annotations

import json
import zipfile

import pytest

from qpot import projects, session
from qpot.schema import migrate_design, parameter_values, set_parameter, validate_parameters


def test_legacy_parameters_migrate_without_losing_references():
    legacy = {
        "dim": 2, "material": "GaAs", "domain": {"L": 100, "N": 64},
        "parameters": {"R": 20, "Vb": 0.228, "n": 7},
        "pieces": [{"op": "mask", "region": {"op": "disk", "args": {
            "center": [0, 0], "radius": "R"}}, "value": "Vb"}],
    }
    migrated, changed = migrate_design(legacy)
    assert changed and migrated["schema_version"] == "1.0"
    assert parameter_values(migrated) == legacy["parameters"]
    assert migrated["pieces"] == legacy["pieces"]
    assert validate_parameters(migrated) == []


def test_integer_parameter_rejects_fractional_sweep_value():
    design = {"parameters": {"n": {"value": 7, "unit": "", "dtype": "int",
                                      "kind": "dimensionless", "role": "lóbulos"}}}
    with pytest.raises(ValueError):
        set_parameter(design, "n", 7.5)


def test_preset_parameterization_includes_nested_geometry():
    from core.composer import preset_to_design
    from qpot.schema import parameterize_preset

    design = parameterize_preset(preset_to_design("finite_well", {}, dim=1))
    length_ref = design["pieces"][0]["region"]["args"]["length"]
    assert isinstance(length_ref, str)
    assert design["parameters"][length_ref]["kind"] == "length"


def test_project_lifecycle_and_reproducible_zip(tmp_path, monkeypatch):
    monkeypatch.setenv(projects.WORKSPACE_ENV, str(tmp_path / "workspace"))
    path = projects.create_project("Mi Anillo", dim=2, material="GaAs")
    assert projects.active_slug() == "mi-anillo"
    assert path.joinpath("history").is_dir()
    rows = projects.list_projects()
    assert rows[0]["active"] is True
    cloned = projects.clone_project("mi-anillo", "copia")
    assert cloned.name == "copia"
    archive = projects.archive_project("mi-anillo")
    assert json.loads((archive / "project.json").read_text())["archived"] is True
    bundle = projects.export_project("copia")
    with zipfile.ZipFile(bundle) as zf:
        assert "copia/design.json" in zf.namelist()
        assert "copia/provenance.json" in zf.namelist()


def test_atomic_save_keeps_history(tmp_path, monkeypatch):
    monkeypatch.setenv(session.SESSION_DIR_ENV, str(tmp_path))
    session.save_design(session.new_design())
    design = session.load_design()
    design["pieces"] = [{"op": "constant", "args": {"value": 0.1}}]
    session.save_design(design)
    assert list((tmp_path / "history").glob("*.json"))
