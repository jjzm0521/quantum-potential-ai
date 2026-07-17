"""
Compatibility helpers for Design contracts and historical agent tasks.

The harness is intentionally file-based:
  task_dir/request.json        structured input for an agent/tool
  task_dir/instructions.md     human-readable task
  task_dir/current_design.json current Design JSON
  task_dir/result.json         expected output from the agent/tool

Quantum Potential AI 1.0 uses qpot.verification as its only execution pipeline.
Historical task readers remain so old runs can be inspected, but this module no
longer launches a second external-agent workflow.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import uuid
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ai.event_log import DEFAULT_RUNS_DIR, RUNS_DIR_ENV
from ai.primitives_spec import design_schema, primitives_documentation
from ai.validators import validate_design
from core.composer import evaluate_design, evaluate_design_1d
from core.materials import MATERIALS
from core.solver import make_grid, solve
from core.solver_1d import make_grid_1d, solve_1d


TASKS_DIR_NAME = "agent_tasks"
RESULT_FILE = "result.json"
ENABLE_RUN_ENV = "AGENT_HARNESS_ENABLE_RUN"
TOOL_ENV_PREFIX = "AGENT_TOOL_"
TIMEOUT_ENV = "AGENT_HARNESS_TIMEOUT_SEC"

PRESET_TOOL_TEMPLATES = {
    "codex": 'codex exec "{instructions_path}"',
    "claude": 'claude -p "@{instructions_path}"',
    "antigravity": 'antigravity-ide "{task_dir}"',
}

PRESET_EXECUTABLES = {
    "codex": ["codex"],
    "claude": ["claude", "claude.cmd"],
    "antigravity": ["antigravity-ide", "antigravity"],
}


@dataclass
class AgentTool:
    name: str
    env_name: str
    command_template: str


@dataclass
class AgentTask:
    task_id: str
    task_dir: Path
    request_path: Path
    instructions_path: Path
    result_path: Path


@dataclass
class AgentRun:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    command: str


def tasks_root() -> Path:
    root = Path(os.environ.get(RUNS_DIR_ENV, DEFAULT_RUNS_DIR))
    return root / TASKS_DIR_NAME


def _new_task_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"agent-{ts}-{uuid.uuid4().hex[:8]}"


def prepare_agent_task(
    design: dict[str, Any],
    *,
    description: str = "",
    goal: str = "describe_and_parameterize_quantum_potential",
    source: str = "streamlit",
    n_states: int = 6,
    original_image: bytes | None = None,
    original_image_ext: str = "png",
    render_png: bytes | None = None,
) -> AgentTask:
    """Create a portable task folder for Codex/Claude/Antigravity/etc."""
    task_id = _new_task_id()
    task_dir = tasks_root() / task_id
    task_dir.mkdir(parents=True, exist_ok=False)

    dim = int(design.get("dim", 2))
    input_files = []
    if original_image is not None:
        ext = original_image_ext.lower().lstrip(".") or "png"
        input_files.append({"path": f"original.{ext}", "role": "source_image"})
    if render_png is not None:
        input_files.append({"path": "render.png", "role": "current_design_render"})

    request = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "goal": goal,
        "description": description,
        "dim": dim,
        "material": design.get("material", "GaAs"),
        "domain": design.get("domain", {}),
        "n_states": n_states,
        "current_design": design,
        "input_files": input_files,
        "expected_result_file": RESULT_FILE,
        "expected_result_schema": {
            "status": "ok | needs_changes | failed",
            "design": "{Design JSON compatible with core.composer}",
            "reasoning": "short explanation",
            "changes_summary": "short summary",
            "confidence": "alta | media | baja",
            "parameterization_notes": "which parameters matter and why",
            "assumptions": ["explicit assumptions made from text/image"],
            "alternatives": ["optional alternative parameterizations for the researcher"],
            "diagnostics": "{optional object}",
        },
        "constraints": [
            "Return valid JSON in result.json.",
            "Use only primitives available for the selected dim.",
            "Keep distances in nm and energies in eV.",
            "Prefer physically plausible semiconductor scales.",
            "Expose the parameters a researcher would likely want to tune.",
            "If the image/text is ambiguous, state assumptions instead of inventing certainty.",
            "Do not remove material/domain unless there is a clear reason.",
        ],
    }

    request_path = task_dir / "request.json"
    design_path = task_dir / "current_design.json"
    instructions_path = task_dir / "instructions.md"
    result_path = task_dir / RESULT_FILE

    _write_json(request_path, request)
    _write_json(design_path, design)
    instructions_path.write_text(_build_instructions(request), encoding="utf-8")

    if original_image is not None:
        (task_dir / f"original.{ext}").write_bytes(original_image)
    if render_png is not None:
        (task_dir / "render.png").write_bytes(render_png)

    return AgentTask(task_id, task_dir, request_path, instructions_path, result_path)


def list_agent_tasks(limit: int = 25) -> list[dict[str, Any]]:
    root = tasks_root()
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        req_path = d / "request.json"
        result_path = d / RESULT_FILE
        if not req_path.exists():
            continue
        try:
            req = _read_json(req_path)
        except Exception:
            req = {}
        rows.append({
            "task_id": d.name,
            "dir": str(d),
            "created_at": req.get("created_at", ""),
            "goal": req.get("goal", ""),
            "dim": req.get("dim", "?"),
            "has_result": result_path.exists(),
        })
        if len(rows) >= limit:
            break
    return rows


def load_task(task_id: str) -> dict[str, Any]:
    return _read_json(tasks_root() / task_id / "request.json")


def load_agent_result(task_id: str) -> tuple[dict[str, Any], list[str]]:
    """Read result.json and validate the returned design when present."""
    result_path = tasks_root() / task_id / RESULT_FILE
    result = _read_json(result_path)
    design = result.get("design")
    if design is None and "pieces" in result:
        design = result
        result = {"status": "ok", "design": design}
    if not isinstance(design, dict):
        return result, ["result.json no trae un campo 'design' válido."]
    return result, _validation_issues_with_grid(design)


def run_local_calculation(task_id: str) -> dict[str, Any]:
    """Run validation + Schrödinger solver locally and write result.json."""
    task_dir = tasks_root() / task_id
    req = _read_json(task_dir / "request.json")
    design = req.get("current_design", {})
    n_states = int(req.get("n_states", 6))

    issues = _validation_issues_with_grid(design)
    diagnostics: dict[str, Any] = {"validator_issues": issues}

    if not issues:
        try:
            diagnostics.update(_solve_summary(design, n_states=n_states))
        except Exception as exc:
            diagnostics["solver_error"] = str(exc)

    result = {
        "status": "ok" if not diagnostics.get("solver_error") else "failed",
        "design": design,
        "reasoning": "Cálculo local: validación numérica y solver Schrödinger sin llamada a API.",
        "changes_summary": "No se modificó el Design; se evaluó su consistencia.",
        "confidence": "media" if issues else "alta",
        "diagnostics": diagnostics,
    }
    _write_json(task_dir / RESULT_FILE, result)
    return result


def run_design_review(task_id: str) -> dict[str, Any]:
    """Review parameterization and schema without solving Schrödinger."""
    task_dir = tasks_root() / task_id
    req = _read_json(task_dir / "request.json")
    design = req.get("current_design", {})
    issues = _validation_issues_with_grid(design)
    report = describe_design_contract(design)

    result = {
        "status": "ok" if not issues else "needs_changes",
        "design": design,
        "reasoning": (
            "Revisión local de parametrización: se inspeccionó si el potencial "
            "queda descrito con primitivas, parámetros y escalas coherentes."
        ),
        "changes_summary": "No se modificó el Design; se generó una revisión paramétrica.",
        "confidence": "alta" if not issues else "media",
        "parameterization_notes": report["parameterization_notes"],
        "assumptions": report["assumptions"],
        "alternatives": report["alternatives"],
        "diagnostics": {
            "validator_issues": issues,
            "design_contract": report,
        },
    }
    _write_json(task_dir / RESULT_FILE, result)
    return result


def describe_design_contract(design: dict[str, Any]) -> dict[str, Any]:
    """Summarize the Design as an inspectable potential specification."""
    dim = int(design.get("dim", 2))
    domain = design.get("domain", {}) if isinstance(design.get("domain"), dict) else {}
    pieces = design.get("pieces", []) if isinstance(design.get("pieces"), list) else []
    piece_summaries = []
    tunable_parameters = []

    for idx, piece in enumerate(pieces):
        if not isinstance(piece, dict):
            piece_summaries.append({"index": idx, "issue": "piece is not an object"})
            continue
        summary = _summarize_piece(idx, piece, dim)
        piece_summaries.append(summary)
        tunable_parameters.extend(summary.get("tunable_parameters", []))

    issues = _validation_issues_with_grid(design)
    return {
        "dim": dim,
        "material": design.get("material", "GaAs"),
        "domain": {
            "L_nm": domain.get("L"),
            "N": domain.get("N"),
            "role": "ventana espacial y discretización para render/validación",
        },
        "pieces": piece_summaries,
        "tunable_parameters": tunable_parameters,
        "parameterization_notes": _parameterization_notes(dim, piece_summaries),
        "assumptions": _local_assumptions(design),
        "alternatives": _parameterization_alternatives(dim, piece_summaries),
        "validator_issues": issues,
    }


def available_agent_tools() -> list[AgentTool]:
    tools = []
    for env_name, value in sorted(os.environ.items()):
        if not env_name.startswith(TOOL_ENV_PREFIX) or not value.strip():
            continue
        name = env_name[len(TOOL_ENV_PREFIX):].lower()
        tools.append(AgentTool(name=name, env_name=env_name, command_template=value))
    return tools


def agent_tool_presets() -> list[dict[str, Any]]:
    """Return copyable tool configs for common agent CLIs."""
    rows = []
    for name, template in PRESET_TOOL_TEMPLATES.items():
        detected_path = _first_executable(PRESET_EXECUTABLES.get(name, [template.split()[0]]))
        rows.append({
            "name": name,
            "env_name": f"{TOOL_ENV_PREFIX}{name.upper()}",
            "command_template": template,
            "detected_on_path": detected_path is not None,
            "detected_path": detected_path or "",
            "local_config_found": _local_config_found(name),
        })
    return rows


def _first_executable(names: list[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _local_config_found(name: str) -> bool:
    home = Path.home()
    if name == "claude":
        return (home / ".claude").exists() or (Path(os.environ.get("LOCALAPPDATA", "")) / "Claude").exists()
    if name == "antigravity":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        return (
            (local / "Programs" / "Antigravity").exists()
            or (local / "Programs" / "Antigravity IDE").exists()
            or (local / "antigravity").exists()
        )
    return False


def render_command(tool: AgentTool, task_id: str) -> str:
    task_dir = tasks_root() / task_id
    values = _command_values(task_dir)
    return tool.command_template.format(**values)


def external_execution_enabled() -> bool:
    return os.environ.get(ENABLE_RUN_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def run_agent_tool(tool_name: str, task_id: str) -> AgentRun:
    raise RuntimeError(
        "El launcher externo fue retirado en 1.0. Abre el agente dentro del repositorio "
        "y usa el CLI qpot; verify/app comparten qpot.verification."
    )


def _build_instructions(request: dict[str, Any]) -> str:
    dim = int(request.get("dim", 2))
    input_files = request.get("input_files", [])
    files_md = "\n".join(
        f"- `{item.get('path')}`: {item.get('role')}"
        for item in input_files
    ) or "- No attached files."
    return f"""# Quantum Potential Agent Task

Goal: {request.get("goal")}
Dimension: {dim}D
Material: {request.get("material")}
Domain: {json.dumps(request.get("domain", {}), ensure_ascii=False)}

## User / App Context

{request.get("description") or "(sin descripción textual)"}

## Attached Files

{files_md}

## What You Should Do

1. Read `request.json` and `current_design.json`.
2. Produce the best parameterized description of the potential, not just a numerical answer.
3. Validate whether the Design is physically plausible and compatible with the composer.
4. Expose assumptions, tunable parameters, and alternative parameterizations.
5. If useful, run local calculations/tests available in this repository.
4. Write `result.json` in this folder.

## Required `result.json`

```json
{{
  "status": "ok",
  "design": {{ "...": "Design JSON compatible with core.composer" }},
  "reasoning": "short explanation",
  "changes_summary": "short summary",
  "confidence": "alta | media | baja",
  "parameterization_notes": "which parameters matter and why",
  "assumptions": ["explicit assumptions made from text/image"],
  "alternatives": ["optional alternative parameterizations"],
  "diagnostics": {{}}
}}
```

The main output is the `design`: it must describe the potential with the right
pieces, geometry, physical scales, and researcher-tunable parameters. You may
return the unchanged design only if it is already the best parameterization.

## Design Schema

{design_schema()}

## Available Primitives

{primitives_documentation(dim=dim)}
"""


def _validation_issues_with_grid(design: dict[str, Any]) -> list[str]:
    dim = int(design.get("dim", 2))
    domain = design.get("domain", {}) if isinstance(design.get("domain"), dict) else {}
    L = float(domain.get("L", 120.0 if dim == 1 else 200.0))
    N = int(domain.get("N", 512 if dim == 1 else 96))

    if dim == 1:
        x = make_grid_1d(L, N)
        return validate_design(design, x_1d=x)

    x, y, X, Y = make_grid(L, N)
    return validate_design(design, X=X, Y=Y)


def _summarize_piece(index: int, piece: dict[str, Any], dim: int) -> dict[str, Any]:
    op = piece.get("op", "?")
    args = piece.get("args", {}) if isinstance(piece.get("args", {}), dict) else {}
    summary: dict[str, Any] = {
        "index": index,
        "label": piece.get("label", op),
        "op": op,
        "enabled": piece.get("enabled", True),
        "role": _piece_role(op, piece),
        "parameters": {},
        "tunable_parameters": [],
    }

    if op == "mask":
        region = piece.get("region", {})
        summary["region"] = region
        summary["value_eV"] = piece.get("value")
        summary["parameters"] = {
            "region": region,
            "value_eV": piece.get("value"),
        }
        summary["tunable_parameters"] = [
            _param(index, "value", "eV", "energía constante dentro de la región"),
            _param(index, "region.args", "nm", "geometría espacial de la zona"),
        ]
        return summary

    if op == "where":
        summary["parameters"] = {
            "region": piece.get("region"),
            "inner": piece.get("inner"),
            "outer": piece.get("outer"),
        }
        summary["tunable_parameters"] = [
            _param(index, "region.args", "nm", "frontera donde cambia la definición"),
            _param(index, "inner/outer", "eV", "potencial dentro y fuera de la región"),
        ]
        return summary

    summary["parameters"] = args
    summary["tunable_parameters"] = [
        _param(index, name, _unit_for_param(name), _param_role(name, op))
        for name in args
    ]
    return summary


def _piece_role(op: str, piece: dict[str, Any]) -> str:
    roles = {
        "gaussian": "pozo o barrera suave localizada",
        "gaussian_1d": "pozo o barrera suave localizada en x",
        "mexican_hat": "anillo o confinamiento radial tipo corona",
        "coulomb": "impureza/carga donadora o aceptora regularizada",
        "linear": "campo eléctrico externo tipo Stark",
        "harmonic": "confinamiento parabólico 1D",
        "harmonic_2d": "confinamiento parabólico 2D",
        "mask": "región de potencial constante con frontera geométrica",
        "where": "definición por partes dentro/fuera de una región",
        "constant": "offset energético global o local",
        "plane": "inclinación lineal espacial",
        "super_gaussian": "pozo/barrera con bordes suaves y centro plano",
        "exp_decay": "cola exponencial o perturbación localizada",
    }
    return roles.get(op, f"componente paramétrica '{op}'")


def _param(index: int, name: str, unit: str, role: str) -> dict[str, Any]:
    return {
        "piece_index": index,
        "name": name,
        "unit": unit,
        "role": role,
    }


def _unit_for_param(name: str) -> str:
    n = name.lower()
    if n in {"depth", "amplitude", "height", "value", "offset", "v0"}:
        return "eV"
    if "center" in n or n in {"sigma", "width", "length", "radius", "r0", "x0", "y0", "regularization"}:
        return "nm"
    if n in {"slope", "force"}:
        return "eV/nm"
    if "omega" in n or "curv" in n:
        return "eV/nm^2"
    if n in {"eps_r", "charge", "n", "k"}:
        return "adimensional"
    return ""


def _param_role(name: str, op: str) -> str:
    n = name.lower()
    if n in {"depth", "amplitude", "height", "value"}:
        return "escala energética; controla profundidad o barrera"
    if "center" in n or n in {"x0", "y0"}:
        return "posición espacial del componente"
    if n in {"sigma", "width", "length", "radius", "r0"}:
        return "tamaño/ancho característico del componente"
    if n in {"slope", "force"}:
        return "intensidad y dirección efectiva del campo externo"
    if n in {"omega_eV", "curvx", "curvy"}:
        return "curvatura del confinamiento"
    if n == "eps_r":
        return "apantallamiento dieléctrico del material"
    if n == "regularization":
        return "suavizado de singularidad/carga puntual"
    if n == "angle":
        return "orientación de la geometría"
    if n == "n":
        return "exponente de forma; ajusta bordes redondeados/cuadrados"
    return f"parámetro de la primitiva {op}"


def _parameterization_notes(dim: int, pieces: list[dict[str, Any]]) -> str:
    if not pieces:
        return "El Design no tiene piezas; falta definir la estructura del potencial."
    ops = [p.get("op", "?") for p in pieces]
    notes = [
        f"El potencial {dim}D queda definido como suma/composición de {len(pieces)} pieza(s): {', '.join(ops)}.",
        "Los parámetros principales a exponer son energías en eV, longitudes en nm y posiciones de cada componente.",
    ]
    if any(op in ops for op in ("mask", "where")):
        notes.append("Hay regiones por partes; conviene exponer la frontera geométrica como parámetro editable.")
    if any("gaussian" in str(op) for op in ops):
        notes.append("Las gaussianas permiten ajustar profundidad, centro y sigma para calibrar forma experimental.")
    if any(op in ops for op in ("linear", "plane")):
        notes.append("El término lineal representa campo externo; debe quedar separado para barridos de Stark.")
    return " ".join(notes)


def _local_assumptions(design: dict[str, Any]) -> list[str]:
    assumptions = []
    if "material" not in design:
        assumptions.append("Material no especificado; se asume GaAs si el cálculo lo necesita.")
    if "domain" not in design:
        assumptions.append("Dominio no especificado; se asume una ventana típica para render/validación.")
    if not design.get("pieces"):
        assumptions.append("No hay piezas; no se puede inferir una estructura física.")
    return assumptions or ["No se agregaron supuestos locales adicionales."]


def _parameterization_alternatives(dim: int, pieces: list[dict[str, Any]]) -> list[str]:
    ops = {p.get("op") for p in pieces}
    alternatives = []
    if "mask" in ops:
        alternatives.append("Reemplazar regiones abruptas `mask` por gaussianas/super_gaussian si se desea borde suave experimental.")
    if any(op in ops for op in ("gaussian", "gaussian_1d")):
        alternatives.append("Usar `mask`/`where` si el investigador necesita pozos con paredes más abruptas.")
    if dim == 2 and "mexican_hat" in ops:
        alternatives.append("Descomponer el anillo en varias gaussianas si la imagen muestra asimetrías o lóbulos.")
    if not alternatives:
        alternatives.append("Agregar términos separados para campo externo, impurezas o asimetrías si forman parte del experimento.")
    return alternatives


def _solve_summary(design: dict[str, Any], n_states: int) -> dict[str, Any]:
    dim = int(design.get("dim", 2))
    domain = design.get("domain", {}) if isinstance(design.get("domain"), dict) else {}
    material = str(design.get("material", "GaAs"))
    m_eff = MATERIALS.get(material, MATERIALS["GaAs"]).m_eff
    L = float(domain.get("L", 120.0 if dim == 1 else 200.0))
    N = int(domain.get("N", 512 if dim == 1 else 96))

    if dim == 1:
        x = make_grid_1d(L, N)
        V = evaluate_design_1d(design, x)
        result = solve_1d(V, x, m_eff, n_states=n_states)
        return {
            "dim": 1,
            "convergence_ok": result.convergence_ok,
            "energies_meV": _round_array(result.energies_meV),
            "grid": {"L": L, "N": N},
            "potential_range_eV": _range_summary(V),
        }

    x, y, X, Y = make_grid(L, N)
    V = evaluate_design(design, X, Y)
    result = solve(V, x, y, m_eff, n_states=n_states)
    return {
        "dim": 2,
        "convergence_ok": result.convergence_ok,
        "energies_meV": _round_array(result.energies_meV),
        "grid": {"L": L, "N": N},
        "potential_range_eV": _range_summary(V),
    }


def _command_values(task_dir: Path) -> dict[str, str]:
    values = {
        "task_dir": str(task_dir),
        "request_path": str(task_dir / "request.json"),
        "instructions_path": str(task_dir / "instructions.md"),
        "current_design_path": str(task_dir / "current_design.json"),
        "result_path": str(task_dir / RESULT_FILE),
    }
    return {k: _shell_quote(v) for k, v in values.items()}


def _shell_quote(value: str) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


def _range_summary(values: np.ndarray) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"min": float("nan"), "max": float("nan")}
    return {
        "min": round(float(finite.min()), 8),
        "max": round(float(finite.max()), 8),
    }


def _round_array(values: np.ndarray) -> list[float]:
    return [round(float(v), 6) for v in values.tolist()]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Quantum Potential agent harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List agent tasks")

    calc = sub.add_parser("local-calc", help="Run local validation + solver for a task")
    calc.add_argument("task_id")

    review = sub.add_parser("design-review", help="Review potential parameterization without solving")
    review.add_argument("task_id")

    val = sub.add_parser("validate-result", help="Validate task result.json")
    val.add_argument("task_id")

    tools = sub.add_parser("tools", help="List configured external tools")
    tools.add_argument("--task-id", default="", help="Also render commands for this task")
    tools.add_argument("--presets", action="store_true", help="Show copyable presets for known tools")

    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_agent_tasks(limit=100), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "local-calc":
        print(json.dumps(run_local_calculation(args.task_id), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "design-review":
        print(json.dumps(run_design_review(args.task_id), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "validate-result":
        result, issues = load_agent_result(args.task_id)
        print(json.dumps({"result": result, "validator_issues": issues}, ensure_ascii=False, indent=2))
        return 0 if not issues else 1

    if args.cmd == "tools":
        rows = []
        for tool in available_agent_tools():
            row = {"name": tool.name, "env_name": tool.env_name}
            if args.task_id:
                row["command"] = render_command(tool, args.task_id)
            rows.append(row)
        if args.presets:
            rows.append({"presets": agent_tool_presets()})
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
