from __future__ import annotations

import json

import pytest

from qpot.geometry_study import compare_designs, save_study


def _well(length: float) -> dict:
    return {
        "schema_version": "1.0",
        "dim": 1,
        "material": "GaAs",
        "domain": {"L": 100.0, "N": 128},
        "pieces": [{
            "op": "mask",
            "region": {"op": "interval", "args": {"center": 0, "length": length}},
            "value": -0.2,
        }],
    }


def test_geometry_study_is_read_only_and_recommends_equivalent_candidate(tmp_path):
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    payload = json.dumps(_well(20.0), indent=2) + "\n"
    reference.write_text(payload, encoding="utf-8")
    candidate.write_text(payload, encoding="utf-8")

    report = compare_designs(
        reference,
        [("intervalo-simple", candidate)],
        n_states=2,
        tolerance_pct=0.1,
        measure_tolerance_pct=0.1,
        objective="levels-and-gaps",
    )

    assert report["recommended_model"] == "intervalo-simple"
    assert report["candidates"][0]["adequate_for_levels_and_gaps"] is True
    assert reference.read_text(encoding="utf-8") == payload
    assert candidate.read_text(encoding="utf-8") == payload
    json_path, png_path = save_study(report, tmp_path / "study.json")
    assert json_path.exists() and png_path.exists()


def test_geometry_study_rejects_uncontrolled_size_change(tmp_path):
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    reference.write_text(json.dumps(_well(20.0)), encoding="utf-8")
    candidate.write_text(json.dumps(_well(10.0)), encoding="utf-8")

    report = compare_designs(
        reference,
        [("demasiado-estrecho", candidate)],
        n_states=2,
        measure_tolerance_pct=5.0,
    )
    row = report["candidates"][0]
    assert row["controlled_geometry_ok"] is False
    assert row["adequate"] is False
    assert report["recommended_model"] == "referencia"


def test_geometry_study_rejects_cross_dimension_comparison(tmp_path):
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    reference.write_text(json.dumps(_well(20.0)), encoding="utf-8")
    candidate.write_text(json.dumps({
        "dim": 2, "material": "GaAs", "domain": {"L": 100, "N": 48},
        "pieces": [{"op": "mask", "region": {"op": "disk", "args": {
            "center": [0, 0], "radius": 10}}, "value": -0.2}],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="dimensión"):
        compare_designs(reference, [("2d", candidate)], n_states=2)
