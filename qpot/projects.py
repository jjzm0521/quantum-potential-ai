"""Local multi-project workspace with atomic writes and immutable history."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ENV = "QPOT_WORKSPACE_DIR"
ACTIVE_FILE = ".active-project"


def workspace_dir() -> Path:
    raw = os.environ.get(WORKSPACE_ENV, "").strip()
    root = Path(raw) if raw else Path.cwd() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("El nombre del proyecto no produce un identificador válido.")
    return slug


def _project_dir(slug: str) -> Path:
    return workspace_dir() / slugify(slug)


def active_slug() -> str | None:
    marker = workspace_dir() / ACTIVE_FILE
    if not marker.exists():
        return None
    slug = marker.read_text(encoding="utf-8").strip()
    return slug if slug and _project_dir(slug).is_dir() else None


def set_active(slug: str) -> Path:
    path = _project_dir(slug)
    if not path.is_dir():
        raise FileNotFoundError(f"Proyecto '{slug}' no existe en {workspace_dir()}.")
    _atomic_text(workspace_dir() / ACTIVE_FILE, path.name + "\n")
    return path


def active_project_dir(*, create_default: bool = True) -> Path:
    slug = active_slug()
    if slug:
        return _project_dir(slug)
    imported = import_legacy_session()
    if imported is not None:
        return imported
    if not create_default:
        raise FileNotFoundError("No hay proyecto activo.")
    return create_project("default", dim=1, material="GaAs", activate=True)


def create_project(name: str, *, dim: int, material: str, activate: bool = True) -> Path:
    from .schema import SCHEMA_VERSION
    slug = slugify(name)
    path = _project_dir(slug)
    if path.exists():
        raise FileExistsError(f"El proyecto '{slug}' ya existe.")
    for sub in ("history", "runs", "exports"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _atomic_json(path / "project.json", {
        "schema_version": "1.0", "slug": slug, "name": name,
        "created_at": now, "updated_at": now, "archived": False,
    })
    _atomic_json(path / "design.json", {
        "schema_version": SCHEMA_VERSION, "dim": int(dim), "material": material,
        "domain": {"L": 120.0, "N": 512} if int(dim) == 1 else {"L": 200.0, "N": 96},
        "pieces": [],
    })
    _atomic_json(path / "target.json", {"description": "", "features": {}, "tolerances": {}})
    if activate:
        set_active(slug)
    return path


def install_demo(source: str | Path, name: str) -> Path:
    """Instala un ejemplo versionado como proyecto independiente y activo."""
    src = Path(source)
    required = ("design.json", "target.json", "agent_assessment.json")
    missing = [filename for filename in required if not (src / filename).is_file()]
    if missing:
        raise FileNotFoundError(
            f"El demo en {src} está incompleto; faltan: {', '.join(missing)}"
        )
    slug = slugify(name)
    dst = _project_dir(slug)
    if dst.exists():
        raise FileExistsError(
            f"El proyecto '{slug}' ya existe. Usa otro nombre o ábrelo con "
            f"`qpot project open {slug}`."
        )
    for sub in ("history", "runs", "exports"):
        (dst / sub).mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _atomic_json(dst / "project.json", {
        "schema_version": "1.0", "slug": slug, "name": name,
        "created_at": now, "updated_at": now, "archived": False,
        "installed_from": str(src),
    })
    for filename in required:
        shutil.copy2(src / filename, dst / filename)
    for source_image in sorted(src.glob("source_image.*")):
        shutil.copy2(source_image, dst / source_image.name)
        break
    return set_active(slug)


def list_projects() -> list[dict[str, Any]]:
    active = active_slug()
    rows: list[dict[str, Any]] = []
    for path in sorted(workspace_dir().iterdir()):
        meta = path / "project.json"
        if not path.is_dir() or not meta.exists():
            continue
        data = json.loads(meta.read_text(encoding="utf-8"))
        data["active"] = path.name == active
        data["path"] = str(path)
        rows.append(data)
    return rows


def clone_project(source: str, destination: str) -> Path:
    src = _project_dir(source)
    dst = _project_dir(destination)
    if not src.is_dir():
        raise FileNotFoundError(f"Proyecto '{source}' no existe.")
    if dst.exists():
        raise FileExistsError(f"Proyecto '{destination}' ya existe.")
    shutil.copytree(src, dst)
    meta = json.loads((dst / "project.json").read_text(encoding="utf-8"))
    meta.update({"slug": dst.name, "name": destination,
                 "created_at": datetime.now(timezone.utc).isoformat(), "archived": False})
    _atomic_json(dst / "project.json", meta)
    return set_active(dst.name)


def archive_project(slug: str) -> Path:
    path = _project_dir(slug)
    meta_path = path / "project.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Proyecto '{slug}' no existe.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["archived"] = True
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(meta_path, meta)
    return path


def export_project(slug: str, output: str | Path | None = None) -> Path:
    path = _project_dir(slug)
    if not path.is_dir():
        raise FileNotFoundError(f"Proyecto '{slug}' no existe.")
    out = (Path(output) if output else workspace_dir() / f"{path.name}.zip").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(path.rglob("*")):
            # The package may intentionally live under project/exports. Never
            # include the destination (or its temporary replacement) in itself.
            if item.is_file() and item.resolve() not in {out, tmp}:
                zf.write(item, arcname=f"{path.name}/{item.relative_to(path)}")
        provenance = json.dumps({
            "python": sys.version, "exported_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2)
        zf.writestr(f"{path.name}/provenance.json", provenance)
    os.replace(tmp, out)
    return out


def import_legacy_session() -> Path | None:
    legacy = Path.cwd() / "session" / "design.json"
    if not legacy.exists():
        return None
    dst = _project_dir("legacy-import")
    if not dst.exists():
        for sub in ("history", "runs", "exports"):
            (dst / sub).mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        _atomic_json(dst / "project.json", {
            "schema_version": "1.0", "slug": "legacy-import", "name": "Legacy import",
            "created_at": now, "updated_at": now, "archived": False,
            "imported_from": str(legacy),
        })
        shutil.copy2(legacy, dst / "design.json")
        _atomic_json(dst / "target.json", {"description": "", "features": {}, "tolerances": {}})
    set_active(dst.name)
    return dst


def revision_path(project: Path, label: str = "design") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return project / "history" / f"{stamp}-{label}.json"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_json(path: Path, data: Any) -> None:
    _atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
