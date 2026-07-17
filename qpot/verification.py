"""Single deterministic verification pipeline shared by CLI, app and agents."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ai.event_log import EventLog
from core import comsol_export, features
from . import render, session
from .schema import design_hash


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _target_match(actual: dict, target: dict | None, assessment: dict | None,
                  current_hash: str) -> dict:
    if (assessment and assessment.get("render_inspected") is True
            and assessment.get("design_hash") == current_hash):
        score = float(assessment.get("score", 0))
        return {
            "ok": score >= 7.0,
            "source": "agent_assessment",
            "score": score,
            "matches": assessment.get("matches", []),
            "mismatches": assessment.get("mismatches", []),
            "suggestions": assessment.get("suggestions", []),
        }
    expected = (target or {}).get("features") or {}
    if not expected:
        return {"ok": False, "source": None,
                "reason": "Falta target.features o una evaluación del agente con render_inspected=true."}
    tolerances = (target or {}).get("tolerances") or {}
    mismatches = []
    matches = []
    for key, wanted in expected.items():
        got = actual.get(key)
        tol = float(tolerances.get(key, 0.0))
        if isinstance(wanted, (int, float)) and isinstance(got, (int, float)):
            ok = abs(float(got) - float(wanted)) <= tol
        else:
            ok = got == wanted
        (matches if ok else mismatches).append({"feature": key, "expected": wanted,
                                                 "actual": got, "tolerance": tol})
    return {"ok": not mismatches, "source": "target.json",
            "matches": matches, "mismatches": mismatches}


def verify_design(design: dict, *, n_states: int = 6, persist: bool = True) -> dict:
    log = EventLog(root=session.artifact("runs")) if persist else None
    if log:
        log.emit("verification_started", {"n_states": n_states})

    all_issues = session.validation_issues(design)
    issues = [item for item in all_issues if not item.startswith("AVISO")]
    warnings = [item for item in all_issues if item.startswith("AVISO")]
    field = session.evaluate_potential(design)
    render_png = session.artifact("render.png")
    render.render_potential(field, render_png, title=f"Potencial ({field['dim']}D)")
    extracted = features.extract_features(field)
    if log:
        log.emit("potential_rendered", {"render_png": str(render_png), "features": extracted})

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "design_hash": design_hash(design),
        "design_dim": int(design.get("dim", 2)),
        "material": design.get("material", "GaAs"),
        "validation": {"ok": not issues, "issues": issues, "warnings": warnings},
        "design_valid": not issues,
        "physics_plausible": not issues and not warnings,
        "render_png": str(render_png),
        "potential_range_eV": session._range_summary(field["V_eV"]),
        "features": extracted,
    }
    try:
        result, solver = session.diagnose_design(design, n_states=n_states)
        wf_png = session.artifact("wavefunctions.png")
        render.render_wavefunctions(result, solver["dim"], wf_png,
                                    n_show=min(4, solver["n_states"]))
        solver["wavefunctions_png"] = str(wf_png)
        report["solver"] = solver
        report["solver_valid"] = solver["solver_valid"]
        report["analytic_benchmark"] = features.harmonic_benchmark(
            field, solver["m_eff"], solver["energies_meV"])
        if log:
            log.emit("solver_completed", solver)
    except Exception as exc:  # a failed solver belongs in the report, not a traceback-only result
        report["solver"] = {"solver_completed": False, "error": str(exc)}
        report["solver_valid"] = False

    comsol_issues = comsol_export.exportability_issues(design)
    report["comsol"] = {"ready": not comsol_issues, "issues": comsol_issues}
    report["comsol_ready"] = not comsol_issues

    target = _read_json(session.artifact("target.json"))
    assessment = _read_json(session.artifact("agent_assessment.json"))
    match = _target_match(extracted, target, assessment, report["design_hash"])
    report["target_match"] = match
    report["ready_to_export"] = bool(
        report["design_valid"] and report["solver_valid"]
        and report["comsol_ready"] and match["ok"]
    )
    report["objective_ok"] = report["ready_to_export"]  # backwards-compatible key

    if log:
        log.emit("verification_completed", {
            "design_valid": report["design_valid"], "solver_valid": report["solver_valid"],
            "comsol_ready": report["comsol_ready"], "target_match": match["ok"],
            "ready_to_export": report["ready_to_export"],
        })
        log.save_json("design.json", design)
        log.save_json("verification.json", report)
        shutil.copy2(render_png, log.dir / "render.png")
        wf = session.artifact("wavefunctions.png")
        if wf.exists():
            shutil.copy2(wf, log.dir / "wavefunctions.png")
        report["run_dir"] = str(log.dir)
        session.artifact("verification.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
