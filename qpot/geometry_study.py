"""Controlled simple-versus-detailed geometry comparison.

This module is intentionally downstream from the certified solver: it loads immutable
Design copies, calls the existing diagnostic pipeline, and writes only study artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from . import projects, session
from .schema import design_hash, migrate_design


def load_design_file(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source}: el Design debe ser un objeto JSON.")
    migrated, _ = migrate_design(data)
    return migrated


def _complexity(design: dict[str, Any]) -> dict[str, int]:
    enabled = [p for p in design.get("pieces", []) if p.get("enabled", True) is not False]

    weights = {
        "disk": 1, "rectangle": 1, "ellipse": 2, "annulus": 2,
        "super_ellipse": 3, "polygon": 3, "rose": 4,
        "epicycloid": 4, "hypocycloid": 4,
        "union": 1, "intersection": 1, "complement": 1,
    }

    def region_nodes(node: Any) -> tuple[int, int]:
        if not isinstance(node, dict):
            return 0, 0
        count = 1 if "op" in node else 0
        score = weights.get(str(node.get("op")), 2) if "op" in node else 0
        child_count, child_score = region_nodes(node.get("region"))
        count += child_count
        score += child_score
        for child in node.get("regions", []):
            child_count, child_score = region_nodes(child)
            count += child_count
            score += child_score
        return count, score

    geometry_nodes = 0
    geometry_score = 0
    for piece in enabled:
        count, score = region_nodes(piece.get("region"))
        geometry_nodes += count
        geometry_score += score
    return {
        "enabled_pieces": len(enabled),
        "geometry_nodes": geometry_nodes,
        "score": len(enabled) + geometry_score,
    }


def _confinement_metrics(result: Any, summary: dict[str, Any]) -> dict[str, Any]:
    dim = int(summary["dim"])
    threshold_eV = float(summary["escape_threshold_meV"]) / 1000.0
    potential = np.asarray(result.V_eV, dtype=float)
    scale = max(float(np.nanmax(np.abs(potential))), 1.0)
    mask = potential < threshold_eV - 1e-12 * scale
    if not np.any(mask):
        raise ValueError("No se encontró una región confinada por debajo del umbral exterior.")

    if dim == 1:
        x = np.asarray(result.x_nm, dtype=float)
        dx = float(abs(x[1] - x[0]))
        density = np.asarray(result.prob_density, dtype=float)
        probabilities = np.sum(density[:, mask], axis=1) * dx
        return {
            "measure": float(np.count_nonzero(mask) * dx),
            "measure_unit": "nm",
            "centroid_nm": [float(np.mean(x[mask]))],
            "aspect_ratio": None,
            "probability_in_qd": [float(v) for v in probabilities],
        }

    x = np.asarray(result.x_nm, dtype=float)
    y = np.asarray(result.y_nm, dtype=float)
    dx = float(abs(x[1] - x[0]))
    dy = float(abs(y[1] - y[0]))
    yy, xx = np.where(mask)
    coords = np.column_stack((x[xx], y[yy]))
    centroid = np.mean(coords, axis=0)
    centered = coords - centroid
    covariance = centered.T @ centered / max(len(coords), 1)
    eigenvalues = np.linalg.eigvalsh(covariance)
    aspect = float(np.sqrt(eigenvalues[-1] / max(eigenvalues[0], 1e-15)))
    densities = np.asarray(result.wavefunctions, dtype=float)
    probabilities = np.sum(densities[:, mask], axis=1) * dx * dy
    return {
        "measure": float(np.count_nonzero(mask) * dx * dy),
        "measure_unit": "nm^2",
        "centroid_nm": [float(v) for v in centroid],
        "aspect_ratio": aspect,
        "probability_in_qd": [float(v) for v in probabilities],
    }


def _percent_error(candidate: float, reference: float, floor: float = 1e-9) -> float:
    return 100.0 * abs(float(candidate) - float(reference)) / max(abs(float(reference)), floor)


def _solve_case(label: str, path: Path, design: dict[str, Any], n_states: int) -> dict[str, Any]:
    issues = [issue for issue in session.validation_issues(design)
              if not issue.startswith("AVISO")]
    if issues:
        raise ValueError(f"{label}: Design inválido: {'; '.join(issues)}")
    result, solver = session.diagnose_design(design, n_states=n_states)
    energies = [float(v) for v in solver["energies_meV"]]
    return {
        "label": label,
        "path": str(path),
        "design_hash": design_hash(design),
        "dimension": int(design.get("dim", 2)),
        "material": design.get("material", "GaAs"),
        "complexity": _complexity(design),
        "solver_valid": bool(solver["solver_valid"]),
        "solver": {
            "energies_meV": energies,
            "gaps_meV": [energies[i + 1] - energies[i] for i in range(len(energies) - 1)],
            "grid_convergence_ok": bool(solver["grid_convergence_ok"]),
            "domain_convergence_ok": bool(solver["domain_convergence_ok"]),
            "boundary_leakage_ok": bool(solver["boundary_leakage_ok"]),
            "n_bound_states": int(solver["n_bound_states"]),
        },
        "geometry": _confinement_metrics(result, solver),
    }


def compare_designs(
    reference_path: str | Path,
    candidates: list[tuple[str, str | Path]],
    *,
    reference_label: str = "referencia",
    n_states: int = 4,
    tolerance_pct: float = 3.0,
    measure_tolerance_pct: float = 5.0,
    aspect_tolerance_pct: float = 10.0,
    gap_tolerance_pct: float = 10.0,
    gap_absolute_tolerance_meV: float = 0.5,
    objective: str = "levels",
) -> dict[str, Any]:
    """Compare candidates with one detailed reference without mutating any Design."""
    if not candidates:
        raise ValueError("Agrega al menos un candidato geométrico.")
    if objective not in {"levels", "levels-and-gaps"}:
        raise ValueError("objective debe ser 'levels' o 'levels-and-gaps'.")
    if min(tolerance_pct, measure_tolerance_pct, aspect_tolerance_pct,
           gap_tolerance_pct, gap_absolute_tolerance_meV) < 0:
        raise ValueError("Las tolerancias no pueden ser negativas.")

    ref_path = Path(reference_path).expanduser().resolve()
    reference_design = load_design_file(ref_path)
    reference = _solve_case(reference_label, ref_path, reference_design, n_states)
    rows: list[dict[str, Any]] = []
    for label, raw_path in candidates:
        path = Path(raw_path).expanduser().resolve()
        design = load_design_file(path)
        if int(design.get("dim", 2)) != reference["dimension"]:
            raise ValueError(f"{label}: la dimensión no coincide con la referencia.")
        if design.get("material", "GaAs") != reference["material"]:
            raise ValueError(f"{label}: el material no coincide con la referencia.")
        row = _solve_case(label, path, design, n_states)
        ref_energies = reference["solver"]["energies_meV"]
        ref_gaps = reference["solver"]["gaps_meV"]
        energy_sensitivity = [
            _percent_error(value, ref_energies[index], floor=0.1)
            for index, value in enumerate(row["solver"]["energies_meV"])
        ]
        gap_sensitivity = [
            _percent_error(value, ref_gaps[index], floor=0.1)
            for index, value in enumerate(row["solver"]["gaps_meV"])
        ]
        gap_absolute_errors = [
            abs(value - ref_gaps[index])
            for index, value in enumerate(row["solver"]["gaps_meV"])
        ]
        measure_error = _percent_error(
            row["geometry"]["measure"], reference["geometry"]["measure"]
        )
        ref_aspect = reference["geometry"]["aspect_ratio"]
        aspect = row["geometry"]["aspect_ratio"]
        aspect_error = None if ref_aspect is None or aspect is None else _percent_error(aspect, ref_aspect)
        probability_delta = [
            abs(value - reference["geometry"]["probability_in_qd"][index])
            for index, value in enumerate(row["geometry"]["probability_in_qd"])
        ]
        row["comparison"] = {
            "energy_sensitivity_pct": energy_sensitivity,
            "max_energy_sensitivity_pct": max(energy_sensitivity, default=float("inf")),
            "gap_sensitivity_pct": gap_sensitivity,
            "max_gap_sensitivity_pct": max(gap_sensitivity, default=float("inf")),
            "gap_absolute_errors_meV": gap_absolute_errors,
            "measure_error_pct": measure_error,
            "aspect_ratio_error_pct": aspect_error,
            "probability_in_qd_absolute_delta": probability_delta,
        }
        row["controlled_geometry_ok"] = bool(
            measure_error <= measure_tolerance_pct
            and (aspect_error is None or aspect_error <= aspect_tolerance_pct)
        )
        row["adequate_for_levels"] = bool(
            reference["solver_valid"]
            and row["solver_valid"]
            and row["controlled_geometry_ok"]
            and row["comparison"]["max_energy_sensitivity_pct"] <= tolerance_pct
        )
        row["gaps_ok"] = bool(all(
            absolute <= gap_absolute_tolerance_meV or relative <= gap_tolerance_pct
            for absolute, relative in zip(gap_absolute_errors, gap_sensitivity)
        ))
        row["adequate_for_levels_and_gaps"] = bool(row["adequate_for_levels"] and row["gaps_ok"])
        row["adequate"] = bool(
            row["adequate_for_levels_and_gaps"]
            if objective == "levels-and-gaps" else row["adequate_for_levels"]
        )
        rows.append(row)

    def recommended(key: str) -> str:
        acceptable = sorted(
            (row for row in rows if row[key]),
            key=lambda row: (row["complexity"]["score"], row["label"]),
        )
        return acceptable[0]["label"] if acceptable else reference["label"]

    recommendations = {
        "levels": recommended("adequate_for_levels"),
        "levels_and_gaps": recommended("adequate_for_levels_and_gaps"),
    }
    recommendation = recommendations["levels_and_gaps" if objective == "levels-and-gaps" else "levels"]
    if recommendations["levels"] == recommendations["levels_and_gaps"]:
        conclusion = f"Usar '{recommendation}' para niveles y separaciones bajo estas tolerancias."
    else:
        conclusion = (
            f"Para niveles basta '{recommendations['levels']}'; para separaciones finas debe "
            f"conservarse '{recommendations['levels_and_gaps']}'."
        )
    return {
        "schema_version": "1.0",
        "method": "controlled_geometry_sensitivity",
        "criteria": {
            "energy_tolerance_pct": float(tolerance_pct),
            "measure_tolerance_pct": float(measure_tolerance_pct),
            "aspect_ratio_tolerance_pct": float(aspect_tolerance_pct),
            "gap_tolerance_pct": float(gap_tolerance_pct),
            "gap_absolute_tolerance_meV": float(gap_absolute_tolerance_meV),
            "selected_objective": objective,
            "acceptance": "solver válido + geometría controlada + observables seleccionados dentro de tolerancia",
        },
        "reference": reference,
        "candidates": rows,
        "recommendations_by_observable": recommendations,
        "recommended_model": recommendation,
        "conclusion": conclusion,
    }


def render_study(report: dict[str, Any], output: str | Path) -> Path:
    import matplotlib.pyplot as plt

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    models = [report["reference"], *report["candidates"]]
    labels = [model["label"] for model in models]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for index, model in enumerate(models):
        energies = model["solver"]["energies_meV"]
        axes[0].scatter([index] * len(energies), energies, s=34)
        for energy in energies:
            axes[0].hlines(energy, index - 0.25, index + 0.25, linewidth=1.2)
    axes[0].set_xticks(range(len(labels)), labels, rotation=18, ha="right")
    axes[0].set_ylabel("Energía (meV)")
    axes[0].set_title("Niveles por geometría")
    axes[0].grid(alpha=0.25)

    candidate_labels = [row["label"] for row in report["candidates"]]
    sensitivities = [row["comparison"]["max_energy_sensitivity_pct"]
                     for row in report["candidates"]]
    colors = ["#2a9d8f" if row["adequate"] else "#e76f51" for row in report["candidates"]]
    axes[1].bar(candidate_labels, sensitivities, color=colors)
    axes[1].axhline(report["criteria"]["energy_tolerance_pct"], color="black",
                    linestyle="--", label="tolerancia")
    axes[1].set_ylabel("máx. $S_E$ (%)")
    axes[1].set_title("Sensibilidad a la simplificación")
    axes[1].tick_params(axis="x", rotation=18)
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.25)
    fig.suptitle(f"Criterio geométrico: {report['conclusion']}", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_study(report: dict[str, Any], json_path: str | Path) -> tuple[Path, Path]:
    destination = Path(json_path).expanduser().resolve()
    projects._atomic_json(destination, report)
    image_path = render_study(report, destination.with_suffix(".png"))
    return destination, image_path
