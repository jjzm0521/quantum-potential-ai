"""Run on the Windows/ASUS host with COMSOL 5.6 + MPh 1.2.3 installed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.materials import MATERIALS
from core.exporter_mph import export_mph_geometry, export_mph


def _tags(java_container) -> list[str]:
    return [str(tag) for tag in java_container.tags()]


def inspect_model(model) -> dict:
    """Inspect the exact geometry/physics/study tree through COMSOL's Java API."""
    component_tags = _tags(model.java.component())
    if not component_tags:
        raise RuntimeError("El .mph no contiene componentes.")
    component = model.java.component(component_tags[0])
    geometry_tags = _tags(component.geom())
    physics_tags = _tags(component.physics())
    study_tags = _tags(model.java.study())
    physics_types = {
        tag: str(component.physics(tag).getType())
        for tag in physics_tags
    }
    schrodinger_tags = [
        tag for tag, feature_type in physics_types.items()
        if feature_type == "SchrodingerEquation"
    ]
    if "geom1" not in geometry_tags or not schrodinger_tags or "std1" not in study_tags:
        raise RuntimeError(
            f"Árbol COMSOL incompleto: geometry={geometry_tags}, physics={physics_tags}, "
            f"physics_types={physics_types}, studies={study_tags}"
        )

    geometry = component.geom("geom1")
    geometry.run()
    domain_count = int(geometry.getNDomains())
    if domain_count < 1:
        raise RuntimeError("La geometría COMSOL no produjo dominios.")

    physics_tag = schrodinger_tags[0]
    physics = component.physics(physics_tag)
    physics_feature_tags = _tags(physics.feature())
    mass_tags = [tag for tag in physics_feature_tags if tag.lower().startswith("meff")]
    potential_tags = [tag for tag in physics_feature_tags if tag.lower().startswith("ve")]
    active_potentials = []
    domain_coverage: dict[int, list[str]] = {domain: [] for domain in range(1, domain_count + 1)}
    for tag in potential_tags:
        feature = physics.feature(tag)
        if not bool(feature.isActive()):
            continue
        entities = [int(value) for value in feature.selection().entities()]
        if not entities:
            entities = list(domain_coverage)
        expression = str(feature.getString("Ve"))
        active_potentials.append({"tag": tag, "domains": entities, "Ve": expression})
        for domain in entities:
            if domain in domain_coverage:
                domain_coverage[domain].append(tag)

    if not mass_tags:
        raise RuntimeError(f"No se encontró la masa efectiva: features={physics_feature_tags}")
    if not active_potentials:
        raise RuntimeError(f"No se encontró energía potencial activa: features={physics_feature_tags}")
    invalid_coverage = {str(k): v for k, v in domain_coverage.items() if len(v) != 1}
    if invalid_coverage:
        raise RuntimeError(
            "Cada dominio debe tener exactamente una asignación final de potencial; "
            f"cobertura inválida={invalid_coverage}"
        )

    mass_feature = physics.feature(mass_tags[0])
    mass_source = str(mass_feature.getString("meffe_psi_src"))
    mass_expression = str(mass_feature.getString("meffe_psi"))
    if mass_source != "userdef" or not mass_expression:
        raise RuntimeError(
            f"Masa efectiva no configurada explícitamente: src={mass_source!r}, "
            f"expr={mass_expression!r}"
        )
    study_feature_tags = _tags(model.java.study("std1").feature())
    if not study_feature_tags:
        raise RuntimeError("El estudio std1 no contiene un paso de valor propio.")
    comments = str(model.java.comments())
    if not comments.startswith("QPOT_METADATA_JSON="):
        raise RuntimeError("El .mph no contiene metadatos QPOT verificables.")
    metadata = json.loads(comments.removeprefix("QPOT_METADATA_JSON="))
    return {
        "component": component_tags[0],
        "geometry_features": _tags(geometry.feature()),
        "domain_count": domain_count,
        "physics": physics_tag,
        "physics_type": physics_types[physics_tag],
        "physics_features": physics_feature_tags,
        "effective_mass_expression": mass_expression,
        "effective_mass_source": mass_source,
        "potentials": active_potentials,
        "domain_coverage": domain_coverage,
        "study_features": study_feature_tags,
        "metadata": metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("design")
    parser.add_argument("result")
    args = parser.parse_args()
    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    result = {"open_ok": False, "inspection_ok": False, "solve_ok": False,
              "energies_meV": [], "inspection": {}, "warnings": [], "errors": []}
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
        result["inspection"] = inspect_model(model)
        result["inspection_ok"] = True
        model.solve()
        result["solve_ok"] = True
        result["potential_samples"] = {}
        for expression in ("schr.Ve", "V_pot(0[m])", "V_pot(50[nm])"):
            try:
                value = model.evaluate(expression)
                result["potential_samples"][expression] = str(value)
            except Exception as exc:
                result["potential_samples"][expression] = {"error": str(exc)}
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
        except Exception as exc:
            result["warnings"].append(f"El modelo se guardó y resolvió, pero no se desconectó: {exc}")
    except Exception as exc:
        result["errors"].append(str(exc))
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    return 0 if (result["open_ok"] and result["inspection_ok"] and result["solve_ok"]
                 and result["energies_meV"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
