"""
qpot.session — estado de sesión basado en archivos para el flujo "agente externo".

El agente (Claude Code / ChatGPT / Codex / Antigravity) y el visor humano comparten un
único Design en `session/design.json`. Todas las operaciones (render, solve, export,
verify) leen ese archivo y escriben artefactos junto a él, sin llamar a ninguna API.

La carpeta de sesión se resuelve así:
  1. variable de entorno QPOT_SESSION_DIR si está definida
  2. <cwd>/session  (por defecto)
"""

from __future__ import annotations

import json
import os
import shutil
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
    d = Path(raw) if raw else Path.cwd() / DEFAULT_SESSION_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def design_path() -> Path:
    return session_dir() / DESIGN_FILE


def artifact(name: str) -> Path:
    return session_dir() / name


def clear_session() -> None:
    """Elimina artefactos de la sesión activa antes de iniciar un proyecto nuevo."""
    sd = session_dir()
    for child in sd.iterdir():
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
    return {"dim": dim, "material": material, "domain": dom, "pieces": []}


def load_design() -> dict:
    p = design_path()
    if not p.exists():
        raise FileNotFoundError(
            f"No hay sesión activa en {p}.\n"
            f"Crea una con:  python -m qpot new --dim 1 --material GaAs"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def save_design(design: dict) -> Path:
    p = design_path()
    p.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
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
    summary = {
        "dim": dim,
        "material": material,
        "m_eff": m_eff,
        "n_states": len(energies),
        "energies_meV": energies,
        "n_bound_states": sum(1 for e in energies if e < 0.0),
        "convergence_ok": bool(res.convergence_ok),
        "grid": {"L": L, "N": N},
        "potential_range_eV": _range_summary(res.V_eV),
    }
    return res, summary


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
        out = Path(out_path) if out_path else sd / "model.mph"
        if dim == 2 and _has_region_assignments(design):
            # .mph NATIVO por geometría + interfaz Schrödinger (lo que el usuario necesita).
            path, msg = export_mph_geometry_or_fallback(design, material, m_eff, n_states, out)
            if path is not None:
                return path, msg
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
    params.update(design.get("parameters") or {})
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
    return design
