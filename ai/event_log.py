"""
Event log append-only para el pipeline IA.

Cada run produce una carpeta `runs/{run_id}/` con:
- `events.jsonl`  — eventos tipados append-only (inmutables)
- `original.<ext>` — imagen original si la hubo
- `render_iter{n}.png` — renders del verifier por iteración

Se inspira en el patrón de OpenHands (event log inmutable como fuente de verdad).
Sirve para auditar qué propuso la IA, qué validó, qué corrigió el refiner y qué
Design final fue exportado a COMSOL.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNS_DIR_ENV = "QUANTUM_RUNS_DIR"
DEFAULT_RUNS_DIR = "runs"


def _runs_root() -> Path:
    import os
    root = os.environ.get(RUNS_DIR_ENV, DEFAULT_RUNS_DIR)
    return Path(root)


class EventLog:
    """Escritor append-only de eventos JSONL para un run."""

    def __init__(self, run_id: str | None = None, root: Path | None = None):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id or f"{ts}-{uuid.uuid4().hex[:8]}"
        base = root or _runs_root()
        self.dir = base / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self._seq = 0
        self._t0 = time.monotonic()

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "dt_ms": int((time.monotonic() - self._t0) * 1000),
            "type": event_type,
            "payload": payload or {},
        }
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")

    def save_blob(self, name: str, data: bytes) -> Path:
        path = self.dir / name
        path.write_bytes(data)
        return path

    def save_json(self, name: str, data: Any) -> Path:
        path = self.dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        return path


def _json_default(o: Any) -> Any:
    if isinstance(o, bytes):
        return f"<bytes len={len(o)}>"
    if hasattr(o, "__dict__"):
        return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
    return str(o)


def list_runs(root: Path | None = None) -> list[dict[str, Any]]:
    """Lista runs existentes con metadatos resumen del primer/último evento."""
    base = root or _runs_root()
    if not base.exists():
        return []
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        ev = d / "events.jsonl"
        if not ev.exists():
            continue
        lines = ev.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        out.append({
            "run_id": d.name,
            "dir": str(d),
            "n_events": len(lines),
            "started": first.get("ts"),
            "ended": last.get("ts"),
            "last_type": last.get("type"),
        })
    return out


def read_events(run_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    base = root or _runs_root()
    ev = base / run_id / "events.jsonl"
    return [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines()]
