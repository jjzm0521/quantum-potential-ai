"""Print the COMSOL Java physics tree of an existing .mph for exporter debugging."""

from __future__ import annotations

import argparse
import json

import mph


def tags(container) -> list[str]:
    return [str(value) for value in container.tags()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("--save-java")
    parser.add_argument("--eval", action="append", dest="expressions")
    args = parser.parse_args()
    client = mph.start()
    model = client.load(args.model)
    if args.save_java:
        model.save(args.save_java)
    tree = {"components": {}}
    if args.expressions:
        tree["evaluations"] = {}
        for expression in args.expressions:
            try:
                value = model.evaluate(expression)
                tree["evaluations"][expression] = str(value)
            except Exception as exc:
                tree["evaluations"][expression] = {"error": str(exc)}
    for component_tag in tags(model.java.component()):
        component = model.java.component(component_tag)
        physics_rows = {}
        for physics_tag in tags(component.physics()):
            physics = component.physics(physics_tag)
            features = {}
            for feature_tag in tags(physics.feature()):
                feature = physics.feature(feature_tag)
                values = {}
                for property_name in (
                    "meffe_psi", "meffe_psi_src", "meffh_psi", "meffh_psi_src",
                    "Ve", "Ve_src",
                ):
                    try:
                        values[property_name] = str(feature.getString(property_name))
                    except Exception:
                        continue
                features[feature_tag] = {
                    "type": str(feature.getType()),
                    "label": str(feature.label()),
                    "active": bool(feature.isActive()),
                    "properties": [str(value) for value in feature.properties()],
                    "values": values,
                }
            physics_rows[physics_tag] = {
                "type": str(physics.getType()),
                "label": str(physics.label()),
                "features": features,
            }
        tree["components"][component_tag] = {
            "geometries": tags(component.geom()),
            "physics": physics_rows,
        }
    tree["studies"] = {
        study_tag: {
            "features": {
                feature_tag: str(model.java.study(study_tag).feature(feature_tag).getType())
                for feature_tag in tags(model.java.study(study_tag).feature())
            }
        }
        for study_tag in tags(model.java.study())
    }
    print(json.dumps(tree, indent=2))
    try:
        client.disconnect()
    except Exception as exc:
        print(json.dumps({"disconnect_warning": str(exc)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
