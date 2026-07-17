"""
qpot.session — estado de sesión basado en archivos para el flujo "agente externo".

El agente y el visor humano comparten el Design del proyecto activo. Todas las operaciones
leen ese archivo y escriben artefactos junto a él, sin llamar a ninguna API.

La carpeta de sesión se resuelve así:
  1. variable de entorno QPOT_SESSION_DIR si está definida
  2. proyecto activo bajo QPOT_WORKSPACE_DIR o <cwd>/workspace
"""

from __future__ import annotations

import json
import os
import shutil
import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from core.composer import (
    evaluate_design,
    evaluate_design_1d,
    design_to_matlab_expr,
    design_to_matlab_expr_1d,
    preset_to_design,
    generate_comsol_recipe,
    resolve_params,
)
from core.materials import MATERIALS
from core.solver import make_grid, solve
from core.solver_1d import make_grid_1d, solve_1d
from core import exporter
from core import comsol_export
from core.exporter_mph import export_mph_or_fallback, export_mph_geometry_or_fallback
from ai.validators import validate_design
from ai.agent_harness import describe_design_contract
from . import projects
from .schema import migrate_design, parameter_values, parameterize_preset, design_hash


SESSION_DIR_ENV = "QPOT_SESSION_DIR"
DEFAULT_SESSION_DIRNAME = "session"
DESIGN_FILE = "design.json"

DEFAULT_DOMAIN = {
    1: {"L": 120.0, "N": 512},
    2: {"L": 200.0, "N": 96},
}

VALID_MATERIALS = set(MATERIALS.keys())


# ---------------------------------------------------------------------------
# Rutas de la sesión
# ---------------------------------------------------------------------------

def session_dir() -> Path:
    raw = os.environ.get(SESSION_DIR_ENV, "").strip()
    d = Path(raw) if raw else projects.active_project_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def design_path() -> Path:
    return session_dir() / DESIGN_FILE


def artifact(name: str) -> Path:
    return session_dir() / name


def clear_session() -> None:
    """Elimina artefactos de la sesión activa antes de iniciar un proyecto nuevo."""
    sd = session_dir()
    current = sd / DESIGN_FILE
    if current.exists():
        history = sd / "history"
        history.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, projects.revision_path(sd, "before-clear"))
    for child in sd.iterdir():
        if child.name in {"history", "runs", "exports", "project.json", "target.json"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def source_image_path() -> Path | None:
    """Devuelve la imagen fuente registrada en la sesión, si existe."""
    sd = session_dir()
    for p in sorted(sd.glob("source_image.*")):
        return p
    return None


# ---------------------------------------------------------------------------
# Crear / cargar / guardar Design
# ---------------------------------------------------------------------------

def default_domain(dim: int) -> dict:
    return dict(DEFAULT_DOMAIN.get(int(dim), DEFAULT_DOMAIN[2]))


def new_design(
    dim: int = 1,
    material: str = "GaAs",
    L: float | None = None,
    N: int | None = None,
) -> dict:
    dim = int(dim)
    dom = default_domain(dim)
    if L is not None:
        dom["L"] = float(L)
    if N is not None:
        dom["N"] = int(N)
    return {"schema_version": "1.0", "dim": dim, "material": material,
            "domain": dom, "pieces": []}


def load_design() -> dict:
    p = design_path()
    if not p.exists():
        raise FileNotFoundError(
            f"No hay sesión activa en {p}.\n"
            f"Crea una con:  python -m qpot new --dim 1 --material GaAs"
        )
    design = json.loads(p.read_text(encoding="utf-8"))
    migrated, _ = migrate_design(design)
    return migrated


def save_design(design: dict) -> Path:
    p = design_path()
    migrated, _ = migrate_design(design)
    if p.exists():
        history = p.parent / "history"
        history.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, projects.revision_path(p.parent))
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------------------
# Helpers de material / dominio / grilla
# ---------------------------------------------------------------------------

def material_m_eff(design: dict) -> tuple[str, float]:
    name = str(design.get("material", "GaAs"))
    mat = MATERIALS.get(name, MATERIALS["GaAs"])
    return name, mat.m_eff


def domain_LN(design: dict) -> tuple[float, int]:
    dim = int(design.get("dim", 2))
    dom = design.get("domain") or {}
    defaults = default_domain(dim)
    L = float(dom.get("L", defaults["L"]))
    N = int(dom.get("N", defaults["N"]))
    return L, N


def evaluate_potential(design: dict) -> dict[str, Any]:
    """Evalúa V sobre la grilla del Design. No resuelve Schrödinger."""
    design = resolve_params(design)
    dim = int(design.get("dim", 2))
    L, N = domain_LN(design)
    if dim == 1:
        x = make_grid_1d(L, N)
        V = evaluate_design_1d(design, x)
        return {"dim": 1, "x_nm": x, "V_eV": V, "L": L, "N": N}
    x, y, X, Y = make_grid(L, N)
    V = evaluate_design(design, X, Y)
    return {"dim": 2, "x_nm": x, "y_nm": y, "V_eV": V, "L": L, "N": N}


def validation_issues(design: dict) -> list[str]:
    """Valida el Design (esquema + estructura + física + numérico) sobre su grilla."""
    design = resolve_params(design)
    dim = int(design.get("dim", 2))
    L, N = domain_LN(design)
    if dim == 1:
        x = make_grid_1d(L, N)
        return validate_design(design, x_1d=x)
    x, y, X, Y = make_grid(L, N)
    return validate_design(design, X=X, Y=Y)


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def solve_design(design: dict, n_states: int = 6):
    """Resuelve Schrödinger sobre el Design. Devuelve (result, summary)."""
    design = resolve_params(design)
    dim = int(design.get("dim", 2))
    material, m_eff = material_m_eff(design)
    L, N = domain_LN(design)

    if dim == 1:
        x = make_grid_1d(L, N)
        V = evaluate_design_1d(design, x)
        res = solve_1d(V, x, m_eff, n_states=n_states)
    else:
        x, y, X, Y = make_grid(L, N)
        V = evaluate_design(design, X, Y)
        res = solve(V, x, y, m_eff, n_states=n_states)

    energies = [round(float(e), 6) for e in res.energies_meV.tolist()]
    escape_threshold = _escape_threshold_meV(res.V_eV, dim)
    summary = {
        "dim": dim,
        "material": material,
        "m_eff": m_eff,
        "n_states": len(energies),
        "energies_meV": energies,
        "escape_threshold_meV": round(escape_threshold, 6),
        "n_bound_states": sum(1 for e in energies if e < escape_threshold),
        "solver_completed": True,
        "convergence_ok": bool(res.convergence_ok),
        "eigensolver_residual_ok": bool(max(res.residuals, default=float("inf")) < 1e-6),
        "max_relative_residual": float(max(res.residuals, default=float("inf"))),
        "orthogonality_error": float(res.orthogonality_error),
        "max_normalization_error": float(max(res.normalization_errors, default=float("inf"))),
        "boundary_probabilities": [round(float(v), 8) for v in res.boundary_probabilities.tolist()],
        "boundary_leakage_ok": bool(max(res.boundary_probabilities, default=1.0) < 1e-3),
        "grid": {"L": L, "N": N},
        "potential_range_eV": _range_summary(res.V_eV),
    }
    return res, summary


def _escape_threshold_meV(V_eV: np.ndarray, dim: int) -> float:
    """Lowest robust exterior potential; states below it cannot escape the domain."""
    if int(dim) == 1:
        n = len(V_eV)
        band = max(2, int(np.ceil(0.05 * n)))
        exterior = np.concatenate((V_eV[:band], V_eV[-band:]))
    else:
        ny, nx = V_eV.shape
        band = max(1, int(np.ceil(0.05 * min(nx, ny))))
        mask = np.zeros_like(V_eV, dtype=bool)
        mask[:band, :] = mask[-band:, :] = True
        mask[:, :band] = mask[:, -band:] = True
        exterior = V_eV[mask]
    finite = exterior[np.isfinite(exterior)]
    return float(np.percentile(finite, 5) * 1000.0) if finite.size else float("-inf")


def _energy_convergence(reference: list[float], candidate: list[float], *, discontinuous: bool) -> dict:
    n = min(len(reference), len(candidate))
    abs_tol = 0.5 if discontinuous else 0.1
    rel_tol = 0.03 if discontinuous else 0.01
    deltas = [abs(candidate[i] - reference[i]) for i in range(n)]
    rel = [deltas[i] / max(abs(reference[i]), abs(candidate[i]), 1e-9) for i in range(n)]
    per_state = [deltas[i] <= abs_tol or rel[i] <= rel_tol for i in range(n)]
    return {
        "ok": bool(n and all(per_state)),
        "absolute_tolerance_meV": abs_tol,
        "relative_tolerance": rel_tol,
        "max_absolute_delta_meV": round(max(deltas, default=float("inf")), 6),
        "max_relative_delta": round(max(rel, default=float("inf")), 8),
        "deltas_meV": [round(v, 6) for v in deltas],
    }


def diagnose_design(design: dict, n_states: int = 6) -> tuple[Any, dict]:
    """Solve and verify eigensolver, grid, domain, normalization and boundary leakage."""
    base = resolve_params(design)
    result, summary = solve_design(base, n_states=n_states)
    dim = int(base.get("dim", 2))
    L, N = domain_LN(base)
    text = json.dumps(base.get("pieces", []))
    discontinuous = any(token in text for token in ('"mask"', '"where"', '"barrier"', '"step"', '"infinite_wall"'))

    refined = copy.deepcopy(base)
    max_n = 1024 if dim == 1 else 256
    if N >= max_n:
        refined_n = None
        grid_check = {"ok": False, "base_N": N, "refined_N": None,
                      "reason": f"N={N} alcanza el límite automático {max_n}; "
                                "ejecuta una convergencia explícita en una máquina con más memoria."}
    else:
        refined_n = min(max_n, max(N + 16, int(round(N * 1.5))))
        refined["domain"]["N"] = refined_n
        _, refined_summary = solve_design(refined, n_states=n_states)
        grid_check = _energy_convergence(summary["energies_meV"], refined_summary["energies_meV"],
                                         discontinuous=discontinuous)
        grid_check.update({"base_N": N, "refined_N": refined_n,
                           "refined_energies_meV": refined_summary["energies_meV"]})

    expanded = copy.deepcopy(base)
    expanded_L = L * 1.2
    if N >= max_n:
        expanded_N = None
        domain_check = {"ok": False, "base_L_nm": L, "expanded_L_nm": expanded_L,
                        "expanded_N": None,
                        "reason": "La expansión preservando dx excedería el límite automático de memoria."}
    else:
        expanded_N = min(max_n, max(N + 2, int(round(N * 1.2))))
        expanded["domain"] = {"L": expanded_L, "N": expanded_N}
        _, expanded_summary = solve_design(expanded, n_states=n_states)
        domain_check = _energy_convergence(summary["energies_meV"], expanded_summary["energies_meV"],
                                           discontinuous=discontinuous)
        domain_check.update({"base_L_nm": L, "expanded_L_nm": expanded_L,
                             "expanded_N": expanded_N,
                             "expanded_energies_meV": expanded_summary["energies_meV"]})

    summary["grid_convergence"] = grid_check
    summary["grid_convergence_ok"] = grid_check["ok"]
    summary["domain_convergence"] = domain_check
    summary["domain_convergence_ok"] = domain_check["ok"]
    summary["solver_valid"] = bool(
        summary["solver_completed"] and summary["eigensolver_residual_ok"]
        and summary["grid_convergence_ok"] and summary["domain_convergence_ok"]
        and summary["boundary_leakage_ok"]
        and summary["orthogonality_error"] < 1e-8
        and summary["max_normalization_error"] < 1e-8
    )
    return result, summary


# ---------------------------------------------------------------------------
# Exportadores
# ---------------------------------------------------------------------------

EXPORT_FORMATS = ("csv", "npz", "m", "mph", "recipe")


def _has_region_assignments(design: dict) -> bool:
    return any(
        piece.get("enabled", True) is not False and piece.get("op") in {"mask", "where"}
        for piece in design.get("pieces", [])
    )


def export_design(
    design: dict,
    fmt: str,
    out_path: str | Path | None = None,
    n_states: int = 6,
    allow_fallback: bool = False,
) -> tuple[Path | None, str]:
    """Exporta el Design al formato pedido. Devuelve (path, mensaje)."""
    fmt = fmt.lower()
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Formato '{fmt}' no soportado. Usa: {', '.join(EXPORT_FORMATS)}")

    dim = int(design.get("dim", 2))
    material, m_eff = material_m_eff(design)
    L, N = domain_LN(design)
    sd = session_dir()

    if fmt == "recipe":
        out = Path(out_path) if out_path else sd / "comsol_recipe.md"
        if dim == 2:
            # Receta por geometría + interfaz Schrödinger (conserva nombres de parámetros).
            text = comsol_export.design_to_comsol_recipe(design, material, m_eff, n_states)
        else:
            text = generate_comsol_recipe(resolve_params(design))
        out.write_text(text, encoding="utf-8")
        return out, f"Receta COMSOL escrita en {out}"

    if fmt == "m" and dim == 2 and _has_region_assignments(design):
        # Script .m por geometría + interfaz Schrödinger (conserva nombres de parámetros).
        out = Path(out_path) if out_path else sd / "comsol_model.m"
        out.write_text(comsol_export.design_to_comsol_m(design, material, m_eff, n_states),
                       encoding="utf-8")
        return out, f"Script COMSOL LiveLink (.m, por geometría) en {out}"

    if fmt == "mph":
        verification_path = sd / "verification.json"
        if not verification_path.exists():
            return None, "Export .mph bloqueado: corre `qpot verify`, inspecciona el render y registra `qpot assess`."
        verified = json.loads(verification_path.read_text(encoding="utf-8"))
        if verified.get("design_hash") != design_hash(design):
            return None, "Export .mph bloqueado: el Design cambió después del último verify."
        if not verified.get("ready_to_export"):
            return None, "Export .mph bloqueado: verification.ready_to_export no es true."
        strict_issues = comsol_export.exportability_issues(design)
        if strict_issues:
            return None, "Export .mph estricto bloqueado:\n  - " + "\n  - ".join(strict_issues)
        out = Path(out_path) if out_path else sd / "model.mph"
        if dim == 2 and _has_region_assignments(design):
            # .mph NATIVO por geometría + interfaz Schrödinger (lo que el usuario necesita).
            path, msg = export_mph_geometry_or_fallback(design, material, m_eff, n_states, out)
            if path is not None:
                return path, msg
            if not allow_fallback:
                return None, msg + "\nUsa --allow-fallback para generar una receta explícitamente."
            # Sin MPh: entregamos la receta (no .m, porque el usuario no usa MATLAB).
            rec = Path(out_path).with_suffix(".md") if out_path else sd / "comsol_recipe.md"
            rec.write_text(
                comsol_export.design_to_comsol_recipe(design, material, m_eff, n_states),
                encoding="utf-8")
            return rec, (f"{msg}\nPara el .mph nativo instala MPh (pip install MPh) con COMSOL. "
                         f"Mientras, generé la receta paso a paso: {rec}")
        # 1D: .mph analítico (con fallback a script .m).
        path, msg = export_mph_or_fallback(design, material, m_eff, n_states, out)
        if path is not None:
            return path, msg
        if not allow_fallback:
            return None, msg + "\nUsa --allow-fallback para generar el script .m."
        m_out = out.with_suffix(".m")
        _write_m_script(design, m_out, material, m_eff, n_states)
        return m_out, f"{msg}\nSe generó el script COMSOL .m como alternativa: {m_out}"

    # csv / npz / m(1D) necesitan un resultado del solver
    res, _ = solve_design(design, n_states=n_states)

    if fmt == "csv":
        out = Path(out_path) if out_path else sd / "eigenvalues.csv"
        out.write_bytes(exporter.to_csv(res))
        return out, f"Eigenvalores (CSV) en {out}"

    if fmt == "npz":
        out = Path(out_path) if out_path else sd / "wavefunctions.npz"
        out.write_bytes(exporter.to_npz(res))
        return out, f"Paquete NumPy (.npz) en {out}"

    if fmt == "m":  # 1D: camino analítico
        out = Path(out_path) if out_path else sd / "comsol_model.m"
        _write_m_script(design, out, material, m_eff, n_states, result=res)
        return out, f"Script COMSOL LiveLink (.m) en {out}"

    return None, "Formato no manejado."


def _write_m_script(
    design: dict,
    out: Path,
    material: str,
    m_eff: float,
    n_states: int,
    result=None,
) -> None:
    dim = int(design.get("dim", 2))
    if result is None:
        result, _ = solve_design(design, n_states=n_states)
    L, N = domain_LN(design)
    params = {"L_nm": L, "N": N, "material": material}
    params.update(parameter_values(design))
    if dim == 1:
        expr = design_to_matlab_expr_1d(design)
        data = exporter.to_comsol_m_1d(result, "qpot_design", params, material, m_eff, expr)
    else:
        expr = design_to_matlab_expr(design)
        data = exporter.to_comsol_m(result, "qpot_design", params, material, m_eff, expr)
    out.write_bytes(data)


# ---------------------------------------------------------------------------
# Contrato del diseño (descripción inspeccionable, reusa ai.agent_harness)
# ---------------------------------------------------------------------------

def describe(design: dict) -> dict[str, Any]:
    return describe_design_contract(resolve_params(design))


def zone_overlap_issues(design: dict) -> list[str]:
    """Zonas de potencial (regiones mask/where) que se solapan — malo para el export a
    COMSOL (cada dominio sólo puede tener un Ve). Vacío = disjuntas (OK)."""
    return comsol_export.zone_overlap_issues(design)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def register_source_image(src: str | Path) -> Path:
    """Copia una imagen a la sesión como source_image.<ext> para que el agente la lea."""
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"No existe la imagen: {src}")
    ext = src.suffix.lower().lstrip(".") or "png"
    # Limpia imágenes previas para que solo haya una fuente activa.
    for old in session_dir().glob("source_image.*"):
        old.unlink()
    dst = session_dir() / f"source_image.{ext}"
    shutil.copyfile(src, dst)
    return dst


def _range_summary(values: np.ndarray) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"min": float("nan"), "max": float("nan")}
    return {"min": round(float(finite.min()), 8), "max": round(float(finite.max()), 8)}


def preset_design(name: str, dim: int, params: dict | None = None) -> dict:
    """Construye un Design a partir de un preset del catálogo legacy."""
    design = preset_to_design(name, params or {}, dim=int(dim))
    design.setdefault("domain", default_domain(int(dim)))
    design.setdefault("material", "GaAs")
    return parameterize_preset(design)
