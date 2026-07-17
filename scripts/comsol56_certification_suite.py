"""Run the mandatory Quantum Potential AI 1.0 case matrix on remote COMSOL 5.6."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

from core.composer import preset_to_design
from qpot.comsol_remote import certify, compare_result
from qpot.schema import migrate_design, parameterize_preset


def _region_case(region: dict, *, value: float = -0.2) -> dict:
    design = {
        "dim": 2,
        "material": "GaAs",
        "domain": {"L": 100.0, "N": 72},
        "pieces": [{"op": "mask", "label": "zona", "region": region, "value": value}],
    }
    return migrate_design(design)[0]


def mandatory_cases() -> dict[str, dict]:
    finite_well = parameterize_preset(preset_to_design("finite_well", {}, dim=1))
    finite_well["material"] = "GaAs"
    finite_well["domain"] = {"L": 120.0, "N": 180}
    cases = {
        "finite-well-1d": finite_well,
        "disk": _region_case({"op": "disk", "args": {"center": [0, 0], "radius": 20}}),
        "rectangle": _region_case({"op": "rectangle", "args": {
            "center": [0, 0], "Lx": 35, "Ly": 22}}),
        "ellipse": _region_case({"op": "ellipse", "args": {
            "center": [0, 0], "a": 22, "b": 13}}),
        "superellipse": _region_case({"op": "super_ellipse", "args": {
            "center": [0, 0], "a": 22, "b": 13, "n": 4}}),
        "annulus": _region_case({"op": "annulus", "args": {
            "center": [0, 0], "r_inner": 9, "r_outer": 24}}),
        "boolean-composition": _region_case({"op": "intersection", "regions": [
            {"op": "disk", "args": {"center": [-6, 0], "radius": 24}},
            {"op": "complement", "region": {"op": "disk", "args": {
                "center": [8, 0], "radius": 10}}},
        ]}),
    }
    cases["cycloidal-crown"] = migrate_design({
        "dim": 2, "material": "GaAs", "domain": {"L": 100.0, "N": 96},
        "parameters": {"R1": 12, "R2": 28, "n": 7, "Vb": 0.228},
        "pieces": [{
            "op": "where", "label": "corona",
            "region": {"op": "intersection", "regions": [
                {"op": "epicycloid", "args": {"center": [0, 0], "R": "R2", "n": "n"}},
                {"op": "complement", "region": {"op": "hypocycloid", "args": {
                    "center": [0, 0], "R": "R1", "n": "n"}}},
            ]},
            "inner": {"op": "constant", "args": {"value": 0}},
            "outer": {"op": "constant", "args": {"value": "Vb"}},
        }],
    })[0]
    cases["two-disjoint-zones"] = migrate_design({
        "dim": 2, "material": "GaAs", "domain": {"L": 100.0, "N": 72},
        "pieces": [
            {"op": "mask", "label": "left", "region": {"op": "disk", "args": {
                "center": [-22, 0], "radius": 11}}, "value": -0.2},
            {"op": "mask", "label": "right", "region": {"op": "disk", "args": {
                "center": [22, 0], "radius": 11}}, "value": -0.2},
        ],
    })[0]
    sweep = _region_case({"op": "disk", "args": {"center": [0, 0], "radius": "R"}})
    sweep["parameters"] = {"R": {
        "value": 16.0, "unit": "nm", "dtype": "float", "kind": "length",
        "role": "radio barrible", "min": 10.0, "max": 30.0,
    }}
    for radius in (16.0, 22.0):
        variant = copy.deepcopy(sweep)
        variant["parameters"]["R"]["value"] = radius
        cases[f"parametric-sweep-R-{int(radius)}"] = variant
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--local",
        action="store_true",
        help="Ejecutar el worker en este equipo (para correr directamente en el ASUS).",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="selected_cases",
        help="Ejecutar sólo este caso (se puede repetir). Por defecto ejecuta toda la matriz.",
    )
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    cases = mandatory_cases()
    unknown = sorted(set(args.selected_cases or []) - set(cases))
    if unknown:
        parser.error(f"Casos desconocidos: {', '.join(unknown)}. Disponibles: {', '.join(cases)}")
    selected = args.selected_cases or list(cases)
    for name in selected:
        design = cases[name]
        case_dir = output / name
        case_dir.mkdir(parents=True, exist_ok=True)
        design_path = case_dir / "design.json"
        design_path.write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
        try:
            if args.local:
                result_path = case_dir / "comsol-result.json"
                worker = Path(__file__).with_name("comsol56_worker.py")
                proc = subprocess.run(
                    [sys.executable, str(worker), str(design_path), str(result_path)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if proc.returncode:
                    detail = proc.stderr.strip() or proc.stdout.strip()
                    if result_path.exists():
                        detail += "\n" + result_path.read_text(encoding="utf-8")
                    raise RuntimeError(f"Worker COMSOL falló (rc={proc.returncode}): {detail}")
                comparison = compare_result(design_path, result_path, case_dir)
            else:
                comparison = certify(design_path, case_dir)
            results[name] = {"ok": bool(comparison["compatible"]), "comparison": comparison}
        except Exception as exc:  # keep the full matrix, but fail the suite at the end
            results[name] = {"ok": False, "error": str(exc)}
    summary_path = output / "certification-summary.json"
    summary_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failures = [name for name, result in results.items() if not result["ok"]]
    print(json.dumps({"summary": str(summary_path), "failed": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
