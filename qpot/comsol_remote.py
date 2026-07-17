"""SSH orchestrator for COMSOL 5.6 certification without storing credentials."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import session


HOST_ENV = "QPOT_COMSOL_SSH_HOST"
REMOTE_DIR_ENV = "QPOT_COMSOL_REMOTE_DIR"
REMOTE_COMMAND_ENV = "QPOT_COMSOL_REMOTE_COMMAND"


def configured() -> tuple[bool, str]:
    missing = [name for name in (HOST_ENV, REMOTE_DIR_ENV, REMOTE_COMMAND_ENV)
               if not os.environ.get(name, "").strip()]
    return (not missing, "Configurado" if not missing else "Faltan: " + ", ".join(missing))


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(f"Falló {' '.join(args[:2])}: {proc.stderr.strip() or proc.stdout.strip()}")


def certify(design_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    ok, reason = configured()
    if not ok:
        raise RuntimeError(reason)
    host = os.environ[HOST_ENV].strip()
    remote_dir = os.environ[REMOTE_DIR_ENV].strip().rstrip("/\\")
    command_template = os.environ[REMOTE_COMMAND_ENV].strip()
    design_path = Path(design_path).resolve()
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    remote_design = f"{remote_dir}/design.json"
    remote_result = f"{remote_dir}/comsol-result.json"

    safe_remote_dir = remote_dir.replace("'", "''")
    _run(["ssh", host, "powershell", "-NoProfile", "-Command",
          f"New-Item -ItemType Directory -Force -Path '{safe_remote_dir}' | Out-Null"])
    _run(["scp", str(design_path), f"{host}:{remote_design}"])
    command = command_template.format(design=remote_design, result=remote_result)
    _run(["ssh", host, command])
    local_result = out / "comsol-result.json"
    _run(["scp", f"{host}:{remote_result}", str(local_result)])
    remote = json.loads(local_result.read_text(encoding="utf-8"))

    design = json.loads(design_path.read_text(encoding="utf-8"))
    _, python_summary = session.solve_design(design, n_states=len(remote.get("energies_meV", [])) or 6)
    py_e = python_summary["energies_meV"]
    co_e = [float(v) for v in remote.get("energies_meV", [])]
    discontinuous = any(token in json.dumps(design.get("pieces", []))
                        for token in ('"mask"', '"where"', '"barrier"', '"step"'))
    tolerance = 0.03 if discontinuous else 0.01
    relative = [abs(a - b) / max(abs(a), abs(b), 1e-9) for a, b in zip(py_e, co_e)]
    comparison = {
        "python_energies_meV": py_e,
        "comsol_energies_meV": co_e,
        "relative_errors": relative,
        "tolerance": tolerance,
        "compatible": bool(remote.get("open_ok") and remote.get("solve_ok") and relative
                           and all(err <= tolerance for err in relative)),
    }
    (out / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    return comparison
