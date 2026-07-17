"""Run on the Windows/ASUS host with COMSOL 5.6 + MPh 1.2.3 installed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.materials import MATERIALS
from core.exporter_mph import export_mph_geometry, export_mph


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("design")
    parser.add_argument("result")
    args = parser.parse_args()
    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    result = {"open_ok": False, "solve_ok": False, "energies_meV": [], "errors": []}
    mph_path = Path(args.result).with_suffix(".mph")
    material = design.get("material", "GaAs")
    m_eff = MATERIALS[material].m_eff
    try:
        if int(design.get("dim", 2)) == 2:
            export_mph_geometry(design, material, m_eff, 6, mph_path)
        else:
            export_mph(design, material, m_eff, 6, mph_path)
        import mph
        client = mph.start()
        model = client.load(str(mph_path))
        result["open_ok"] = True
        model.solve()
        result["solve_ok"] = True
        last_error = None
        for expression, scale in (("lambda", 1000.0), ("schr.E", 1000.0), ("eig", 1000.0)):
            try:
                values = model.evaluate(expression)
                result["energies_meV"] = sorted(float(v.real) * scale for v in values)[:6]
                result["eigenvalue_expression"] = expression
                break
            except Exception as exc:
                last_error = exc
        if not result["energies_meV"]:
            raise RuntimeError(f"No se pudo evaluar el espectro de COMSOL 5.6: {last_error}")
        try:
            client.disconnect()
        except Exception:
            pass
    except Exception as exc:
        result["errors"].append(str(exc))
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    return 0 if result["open_ok"] and result["solve_ok"] and result["energies_meV"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

