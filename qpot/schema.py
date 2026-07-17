"""Versioned Design schema and backwards-compatible parameter migration."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any


SCHEMA_VERSION = "1.0"
PARAMETER_DTYPES = {"float", "int", "enum"}
PARAMETER_KINDS = {
    "length", "energy", "angle", "dimensionless", "energy_per_length",
    "energy_per_length2", "inverse_length", "other",
}


def design_hash(design: dict[str, Any]) -> str:
    normalized, _ = migrate_design(design)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _metadata_for_name(name: str, value: Any, *, role: str = "") -> dict[str, Any]:
    n = name.lower()
    integer_names = {"n", "k", "cycles", "ciclos", "nshape", "nexp"}
    if isinstance(value, bool):
        dtype = "enum"
    elif n in integer_names:
        dtype = "int"
    else:
        dtype = "float"
    if n in integer_names | {"charge", "eps_r"}:
        unit, kind = "", "dimensionless"
    elif n in {"theta", "phi"} or "angle" in n or n.endswith("deg"):
        unit, kind = "deg", "angle"
    elif n == "de" or n.startswith("v") or any(t in n for t in ("depth", "amplitude", "height", "barrier")):
        unit, kind = "eV", "energy"
    elif "omega" in n or "curv" in n:
        unit, kind = "eV/nm^2", "energy_per_length2"
    elif "slope" in n or "field" in n:
        unit, kind = "eV/nm", "energy_per_length"
    elif "alpha" in n:
        unit, kind = "1/nm", "inverse_length"
    else:
        unit, kind = "nm", "length"
    return {
        "value": value,
        "unit": unit,
        "dtype": dtype,
        "kind": kind,
        "role": role or f"Parámetro {name}",
    }


def normalize_parameter(name: str, raw: Any) -> dict[str, Any]:
    """Return a v1 parameter record from either a legacy scalar or v1 record."""
    if not isinstance(raw, dict) or "value" not in raw:
        return _metadata_for_name(name, raw)
    out = copy.deepcopy(raw)
    defaults = _metadata_for_name(name, out["value"], role=str(out.get("role", "")))
    for key, value in defaults.items():
        out.setdefault(key, value)
    return out


def migrate_design(design: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Migrate a Design to schema 1.0 without changing named references in pieces."""
    out = copy.deepcopy(design)
    changed = out.get("schema_version") != SCHEMA_VERSION
    out["schema_version"] = SCHEMA_VERSION
    params = out.get("parameters") or {}
    normalized = {name: normalize_parameter(name, raw) for name, raw in params.items()}
    if normalized != params:
        changed = True
    if normalized or "parameters" in out:
        out["parameters"] = normalized
    return out, changed


def parameter_values(design: dict[str, Any]) -> dict[str, Any]:
    return {
        name: normalize_parameter(name, raw)["value"]
        for name, raw in (design.get("parameters") or {}).items()
    }


def validate_parameters(design: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    params = design.get("parameters") or {}
    if not isinstance(params, dict):
        return ["'parameters' debe ser un objeto."]
    for name, raw in params.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(name)):
            issues.append(f"Parámetro '{name}': nombre inválido para Python/COMSOL.")
            continue
        p = normalize_parameter(str(name), raw)
        dtype = p.get("dtype")
        kind = p.get("kind")
        value = p.get("value")
        if dtype not in PARAMETER_DTYPES:
            issues.append(f"Parámetro '{name}': dtype={dtype!r} no soportado.")
        if kind not in PARAMETER_KINDS:
            issues.append(f"Parámetro '{name}': kind={kind!r} no soportado.")
        if dtype == "int" and (not isinstance(value, int) or isinstance(value, bool)):
            issues.append(f"Parámetro '{name}': value debe ser entero.")
        if dtype == "float" and not isinstance(value, (int, float)):
            issues.append(f"Parámetro '{name}': value debe ser numérico.")
        if "min" in p and isinstance(value, (int, float)) and value < p["min"]:
            issues.append(f"Parámetro '{name}': value={value} < min={p['min']}.")
        if "max" in p and isinstance(value, (int, float)) and value > p["max"]:
            issues.append(f"Parámetro '{name}': value={value} > max={p['max']}.")
    return issues


def set_parameter(design: dict[str, Any], name: str, value: Any) -> None:
    params = design.setdefault("parameters", {})
    if name in params:
        record = normalize_parameter(name, params[name])
        dtype = record["dtype"]
        if dtype == "int":
            if isinstance(value, float) and not value.is_integer():
                raise ValueError(f"'{name}' es entero; {value} no es válido.")
            value = int(value)
        if "min" in record and value < record["min"]:
            raise ValueError(f"'{name}' debe ser >= {record['min']}.")
        if "max" in record and value > record["max"]:
            raise ValueError(f"'{name}' debe ser <= {record['max']}.")
        record["value"] = value
        params[name] = record
    else:
        params[name] = _metadata_for_name(name, value)


def parameterize_preset(design: dict[str, Any]) -> dict[str, Any]:
    """Expose scalar preset arguments as named, typed parameters.

    The walk includes nested regions and profiles (for example, the length of an interval
    inside a finite-well mask). Existing named references are left untouched. Lists such
    as centers remain grouped because the UI already edits them as vectors.
    """
    out, _ = migrate_design(design)
    params = out.setdefault("parameters", {})

    def expose(node: dict[str, Any], *, prefix: str, role_label: str,
               path: tuple[str, ...] = ()) -> None:
        args = node.get("args")
        if isinstance(args, dict):
            for key, value in list(args.items()):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                suffix = "_".join((*path, key)) if path else key
                name = f"{prefix}_{suffix}"
                params[name] = _metadata_for_name(
                    key, value, role=f"{key} de {role_label}"
                )
                args[key] = name
        if node.get("op") == "mask" and isinstance(node.get("value"), (int, float)):
            suffix = "_".join((*path, "value")) if path else "value"
            name = f"{prefix}_{suffix}"
            params[name] = _metadata_for_name(
                "value", node["value"], role=f"Potencial de {role_label}"
            )
            node["value"] = name
        for child_key in ("region", "inner", "outer"):
            child = node.get(child_key)
            if isinstance(child, dict):
                expose(child, prefix=prefix, role_label=role_label,
                       path=(*path, child_key))
        for child_index, child in enumerate(node.get("regions") or []):
            if isinstance(child, dict):
                expose(child, prefix=prefix, role_label=role_label,
                       path=(*path, f"region{child_index}"))

    for index, piece in enumerate(out.get("pieces", [])):
        label = re.sub(r"[^A-Za-z0-9]+", "_", str(piece.get("label") or piece.get("op") or f"p{index}"))
        expose(piece, prefix=f"p{index}_{label}",
               role_label=str(piece.get("label", piece.get("op"))))
    return out
