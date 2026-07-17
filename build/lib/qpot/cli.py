"""
qpot.cli — interfaz de línea de comandos.

Cada subcomando opera sobre el Design del proyecto activo. La salida está
pensada para que un LLM (o un humano) la lea fácilmente: acciones imprimen un mensaje
corto; consultas (state, describe, solve, verify) imprimen JSON.

    python -m qpot <comando> [opciones]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import session, render, verification, projects
from .schema import migrate_design, set_parameter, normalize_parameter, design_hash
from core import features as _features
from core import image_analysis as _image_analysis


# ---------------------------------------------------------------------------
# Helpers de salida
# ---------------------------------------------------------------------------

def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ok(msg: str) -> None:
    print(msg)


def _parse_value(raw: str):
    """Convierte un valor de texto a python: JSON si se puede, si no string."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _load_args_json(raw: str | None) -> dict:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--args debe ser un objeto JSON, p.ej. '{\"sigma\": 5}'")
    return data


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_new(args) -> int:
    session.clear_session()
    design = session.new_design(dim=args.dim, material=args.material, L=args.L, N=args.N)
    path = session.save_design(design)
    _ok(f"Sesión nueva creada: {path}\nDim={design['dim']}  Material={design['material']}  "
        f"Domain={design['domain']}  Piezas=0")
    return 0


def cmd_state(args) -> int:
    _print_json(session.load_design())
    return 0


def cmd_describe(args) -> int:
    _print_json(session.describe(session.load_design()))
    return 0


def cmd_render(args) -> int:
    design = session.load_design()
    field = session.evaluate_potential(design)
    out = Path(args.out) if args.out else session.artifact("render.png")
    render.render_potential(field, out, title=f"Potencial ({field['dim']}D)")
    rng = session._range_summary(field["V_eV"])
    msg = (f"Render escrito en {out}\n"
           f"Dim={field['dim']}  Grilla L={field['L']} nm N={field['N']}  "
           f"V_min={rng['min']} eV  V_max={rng['max']} eV\n"
           f"→ Abre/lee el PNG para VER el potencial.")
    target = out
    if args.html:
        html = session.artifact("potential.html")
        render.render_potential_html(field, html)
        msg += f"\nHTML 3D interactivo: {html} (ábrelo en el navegador, sin servidor)"
        target = html
    _ok(msg)
    if args.open:
        import webbrowser
        webbrowser.open(target.resolve().as_uri())
    return 0


def cmd_set(args) -> int:
    design = session.load_design()
    pieces = design.get("pieces", [])
    if not (0 <= args.index < len(pieces)):
        _ok(f"Índice {args.index} fuera de rango (hay {len(pieces)} piezas).")
        return 1
    piece = pieces[args.index]
    value = _parse_value(args.value)
    if args.param in ("value", "label", "enabled"):
        piece[args.param] = value
    else:
        piece.setdefault("args", {})[args.param] = value
    session.save_design(design)
    _ok(f"Pieza #{args.index} ({piece.get('op')}): {args.param} = {value!r}")
    return 0


def cmd_add(args) -> int:
    design = session.load_design()
    if args.json:
        piece = json.loads(args.json)
        if not isinstance(piece, dict):
            _ok("--json debe ser un objeto JSON de una pieza.")
            return 1
    else:
        if not args.op:
            _ok("Falta 'op' (o usa --json para una pieza completa como mask/where).")
            return 1
        piece = {"op": args.op, "args": _load_args_json(args.args)}
        if args.label:
            piece["label"] = args.label
    design.setdefault("pieces", []).append(piece)
    session.save_design(design)
    _ok(f"Pieza agregada en índice {len(design['pieces']) - 1}: {piece.get('op')}")
    return 0


def cmd_remove(args) -> int:
    design = session.load_design()
    pieces = design.get("pieces", [])
    if not (0 <= args.index < len(pieces)):
        _ok(f"Índice {args.index} fuera de rango (hay {len(pieces)} piezas).")
        return 1
    removed = pieces.pop(args.index)
    session.save_design(design)
    _ok(f"Pieza #{args.index} eliminada ({removed.get('op')}). Quedan {len(pieces)}.")
    return 0


def _set_enabled(index: int, enabled: bool) -> int:
    design = session.load_design()
    pieces = design.get("pieces", [])
    if not (0 <= index < len(pieces)):
        _ok(f"Índice {index} fuera de rango (hay {len(pieces)} piezas).")
        return 1
    pieces[index]["enabled"] = enabled
    session.save_design(design)
    _ok(f"Pieza #{index} {'habilitada' if enabled else 'deshabilitada'}.")
    return 0


def cmd_enable(args) -> int:
    return _set_enabled(args.index, True)


def cmd_disable(args) -> int:
    return _set_enabled(args.index, False)


def cmd_material(args) -> int:
    design = session.load_design()
    if args.name not in session.VALID_MATERIALS:
        _ok(f"Material '{args.name}' desconocido. Válidos: {sorted(session.VALID_MATERIALS)}")
        return 1
    design["material"] = args.name
    session.save_design(design)
    _ok(f"Material = {args.name}")
    return 0


def cmd_domain(args) -> int:
    design = session.load_design()
    dom = design.setdefault("domain", session.default_domain(int(design.get("dim", 2))))
    if args.L is not None:
        dom["L"] = float(args.L)
    if args.N is not None:
        dom["N"] = int(args.N)
    session.save_design(design)
    _ok(f"Dominio = {dom}")
    return 0


def cmd_param(args) -> int:
    design = session.load_design()
    params = design.setdefault("parameters", {})
    if args.value is None:
        params.pop(args.name, None)
        session.save_design(design)
        _ok(f"parámetro '{args.name}' eliminado. parameters = {params}")
        return 0
    value = _parse_value(args.value)
    set_parameter(design, args.name, value)
    session.save_design(design)
    _ok(f"parameters['{args.name}'] = {normalize_parameter(args.name, design['parameters'][args.name])!r}  "
        f"(referencia en piezas como \"{args.name}\")")
    return 0


def cmd_from_preset(args) -> int:
    params = json.loads(args.params) if args.params else {}
    design = session.preset_design(args.name, dim=args.dim, params=params)
    # Hereda material/dominio de la sesión actual si existe (no los pierde el preset).
    try:
        prev = session.load_design()
    except FileNotFoundError:
        prev = None
    if prev is not None:
        if prev.get("material"):
            design["material"] = prev["material"]
        if int(prev.get("dim", 0)) == int(args.dim) and isinstance(prev.get("domain"), dict):
            design["domain"] = prev["domain"]
    session.clear_session()
    path = session.save_design(design)
    _ok(f"Preset '{args.name}' cargado en {path} ({len(design.get('pieces', []))} piezas, "
        f"material={design.get('material')}).")
    return 0


def cmd_set_image(args) -> int:
    dst = session.register_source_image(args.path)
    _ok(f"Imagen fuente registrada: {dst}\n"
        f"→ Léela tú mismo (el agente) para diseñar/comparar el potencial.")
    return 0


def cmd_analyze_image(args) -> int:
    """Visión clásica (sin API): sugiere preset + params iniciales desde la foto."""
    suggestion = _image_analysis.analyze_image(args.path)
    # Registra la imagen como fuente para que verify la compare luego.
    dst = session.register_source_image(args.path)
    suggestion["registered_as"] = str(dst)
    suggestion["next_action"] = (
        "Sugerencia de ARRANQUE (no aplicada). Tú decides: usa "
        "`qpot from-preset <suggested_preset> --dim <suggested_dim> "
        "--params '<suggested_params>'`, luego `qpot verify` y refina."
    )
    _print_json(suggestion)
    return 0


def cmd_clean(args) -> int:
    session.clear_session()
    _ok(f"Sesión limpiada: {session.session_dir()}")
    return 0


def cmd_validate(args) -> int:
    design = session.load_design()
    issues = session.validation_issues(design)
    _print_json({"ok": not issues, "issues": issues})
    return 0 if not issues else 1


def cmd_solve(args) -> int:
    design = session.load_design()
    res, summary = session.solve_design(design, n_states=args.n_states)
    # Artefactos
    wf_png = session.artifact("wavefunctions.png")
    render.render_wavefunctions(res, summary["dim"], wf_png, n_show=min(4, summary["n_states"]))
    csv_path = session.artifact("eigenvalues.csv")
    from core import exporter
    csv_path.write_bytes(exporter.to_csv(res))
    result_json = session.artifact("result.json")
    result_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_out = dict(summary)
    summary_out["artifacts"] = {
        "wavefunctions_png": str(wf_png),
        "eigenvalues_csv": str(csv_path),
        "result_json": str(result_json),
    }
    _print_json(summary_out)
    return 0


def cmd_verify(args) -> int:
    """Herramienta del loop: render + validación + solve → señal objetiva para el agente."""
    design = session.load_design()
    report = verification.verify_design(design, n_states=args.n_states, persist=True)
    _print_json(report)
    # A missing target prevents ready_to_export, but does not make a valid numerical
    # verification fail at the shell level.
    return 0 if report["design_valid"] and report["solver_valid"] else 1


def _cmd_verify_legacy(args) -> int:
    """Previous inline implementation kept temporarily for reference."""
    design = session.load_design()
    report: dict = {"design_dim": int(design.get("dim", 2)),
                    "material": design.get("material", "GaAs")}

    # 1. Validación. Los "AVISO:" no bloquean objective_ok: son juicio del agente
    # (p. ej. paredes de confinamiento grandes pero intencionales).
    all_issues = session.validation_issues(design)
    issues = [i for i in all_issues if not i.startswith("AVISO")]
    warnings = [i for i in all_issues if i.startswith("AVISO")]
    report["validation"] = {"ok": not issues, "issues": issues, "warnings": warnings}

    # 2. Render del potencial (para que el agente lo VEA)
    field = session.evaluate_potential(design)
    render_png = session.artifact("render.png")
    render.render_potential(field, render_png, title=f"Potencial ({field['dim']}D)")
    report["render_png"] = str(render_png)
    report["potential_range_eV"] = session._range_summary(field["V_eV"])

    # 2b. Features cuantitativas: nº de pozos, posiciones, simetría → el Refiner
    # compara con NÚMEROS, no adivinando sobre el PNG.
    try:
        report["features"] = _features.extract_features(field)
    except Exception as exc:  # noqa: BLE001
        report["features"] = {"error": str(exc)}

    # 3. Solve (diagnóstico físico)
    try:
        res, summary = session.solve_design(design, n_states=args.n_states)
        wf_png = session.artifact("wavefunctions.png")
        render.render_wavefunctions(res, summary["dim"], wf_png,
                                    n_show=min(4, summary["n_states"]))
        report["solver"] = {
            "convergence_ok": summary["convergence_ok"],
            "energies_meV": summary["energies_meV"],
            "n_bound_states": summary["n_bound_states"],
            "wavefunctions_png": str(wf_png),
        }
        # Contraste analítico: ħω del fondo del pozo vs E1−E0 numérico.
        try:
            report["analytic_benchmark"] = _features.harmonic_benchmark(
                field, summary["m_eff"], summary["energies_meV"])
        except Exception as exc:  # noqa: BLE001
            report["analytic_benchmark"] = {"applicable": False, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        report["solver"] = {"error": str(exc)}

    # 3b. Zonas de potencial disjuntas (para que el export a COMSOL sea fiel)
    overlap = session.zone_overlap_issues(design)
    report["zone_overlap"] = {"ok": not overlap, "issues": overlap}

    # 4. Imagen fuente → instrucción de comparación visual
    feats = report.get("features", {})
    feats_txt = _features_summary(feats)
    src = session.source_image_path()
    if src is not None:
        report["source_image"] = str(src)
        report["visual_check"] = (
            f"{feats_txt} Hay imagen fuente: COMPÁRALA con render_png y con estos números. "
            "¿Coinciden número de pozos/barreras, posiciones, simetría y escalas? "
            "Si no, ajusta piezas y repite verify."
        )
    else:
        report["visual_check"] = (
            f"{feats_txt} No hay imagen fuente: compara estos números y el render_png "
            "contra la descripción textual del objetivo."
        )

    # 5. Veredicto objetivo (la calificación final la pone el agente)
    objective_ok = (not issues) and report["solver"].get("convergence_ok", False)
    report["objective_ok"] = bool(objective_ok)
    report["next_actions"] = _verify_hints(issues, report["solver"])
    if overlap:
        report["next_actions"].insert(
            0, "Hay zonas de potencial que se SOLAPAN; hazlas disjuntas "
               "(usa complement/intersection) o el .mph a COMSOL no coincidirá.")

    _print_json(report)
    return 0 if objective_ok else 1


def _features_summary(feats: dict) -> str:
    """Resumen en lenguaje natural de las features para el campo visual_check."""
    if not feats or "error" in feats:
        return "No se pudieron extraer features cuantitativas."
    nw = feats.get("n_wells", 0)
    parts = [f"Detecté {nw} pozo(s)"]
    if feats.get("well_positions_nm"):
        parts.append(f"en x={feats['well_positions_nm']} nm")
    elif feats.get("well_centroids_nm"):
        parts.append(f"en {feats['well_centroids_nm']} nm")
    if feats.get("well_depths_meV"):
        parts.append(f"profundidad {feats['well_depths_meV']} meV")
    nb = feats.get("n_barriers")
    if nb:
        parts.append(f"{nb} barrera(s)")
    if feats.get("symmetric") is not None:
        parts.append("simétrico" if feats["symmetric"] else "asimétrico")
    if feats.get("ring_like"):
        parts.append("forma de anillo")
    if feats.get("radial_symmetry"):
        parts.append("simetría radial")
    return ", ".join(parts) + "."


def _verify_hints(issues: list[str], solver: dict) -> list[str]:
    hints: list[str] = []
    if issues:
        hints.append("Resuelve los issues de validación con `qpot set` / `qpot add` / `qpot remove`.")
    if "error" in solver:
        hints.append("El solver falló: revisa dominio (L/N) y que el potencial tenga estructura.")
    elif solver.get("n_bound_states", 0) == 0:
        hints.append("No hay estados ligados: ¿el pozo es suficientemente profundo/ancho? "
                     "Ajusta 'value'/'depth' o el dominio.")
    if not hints:
        hints.append("Todo objetivo OK. Revisa el PNG y, si coincide con el objetivo, exporta.")
    return hints


def cmd_sweep(args) -> int:
    """Barrido paramétrico E_n(parámetro) — la gráfica clásica de análisis (sin COMSOL).

    Barre un parámetro nombrado (bloque `parameters`) o, con --piece, un arg de una
    pieza. Resuelve Schrödinger en cada punto y guarda sweep.csv + sweep.png.
    """
    import copy as _copy

    try:
        lo_s, hi_s, n_s = args.range.split(":")
        lo, hi, n_pts = float(lo_s), float(hi_s), int(n_s)
    except ValueError:
        _ok("Formato de --range inválido; usa a:b:n  (p. ej. 0.1:0.5:9)")
        return 1
    if n_pts < 2:
        _ok("--range necesita al menos 2 puntos.")
        return 1

    base = session.load_design()
    if args.piece is None:
        params = base.get("parameters") or {}
        if args.name not in params:
            _ok(f"'{args.name}' no está en `parameters` {list(params)}. "
                f"Defínelo con `qpot param {args.name} <valor>` o usa --piece IDX.")
            return 1
    else:
        pieces = base.get("pieces", [])
        if not (0 <= args.piece < len(pieces)):
            _ok(f"Índice --piece {args.piece} fuera de rango (hay {len(pieces)} piezas).")
            return 1

    values = [lo + (hi - lo) * i / (n_pts - 1) for i in range(n_pts)]
    rows: list[dict] = []
    energies_all: list[list[float]] = []
    for v in values:
        d = _copy.deepcopy(base)
        if args.piece is None:
            set_parameter(d, args.name, v)
        else:
            piece = d["pieces"][args.piece]
            if args.name in ("value",):
                piece[args.name] = v
            else:
                piece.setdefault("args", {})[args.name] = v
        try:
            _, summary = session.solve_design(d, n_states=args.n_states)
            energies = summary["energies_meV"]
            rows.append({"value": v, "ok": True, "energies_meV": energies,
                         "n_bound_states": summary["n_bound_states"]})
            energies_all.append(energies)
        except Exception as exc:  # noqa: BLE001
            rows.append({"value": v, "ok": False, "error": str(exc)})
            energies_all.append([])

    # Artefactos: CSV (valor, E0..Ek) + PNG
    csv_path = session.artifact("sweep.csv")
    n_max = max((len(e) for e in energies_all), default=0)
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write(args.name + "," + ",".join(f"E{i}_meV" for i in range(n_max)) + "\n")
        for row, es in zip(rows, energies_all):
            fh.write(f"{row['value']}" + "".join(f",{e}" for e in es) + "\n")
    png_path = session.artifact("sweep.png")
    if any(energies_all):
        render.render_sweep(values, energies_all, args.name, png_path)

    ok_pts = sum(1 for r in rows if r["ok"])
    _print_json({
        "param": args.name,
        "piece": args.piece,
        "n_points": n_pts,
        "n_solved": ok_pts,
        "results": rows,
        "artifacts": {"csv": str(csv_path),
                      "png": str(png_path) if any(energies_all) else None},
        "note": "El Design en sesión NO cambió; el barrido usa copias. "
                "MIRA sweep.png para el comportamiento E_n(parámetro).",
    })
    return 0 if ok_pts == n_pts else 1


def cmd_export(args) -> int:
    design = session.load_design()
    path, msg = session.export_design(design, args.format, out_path=args.out,
                                      n_states=args.n_states,
                                      allow_fallback=getattr(args, "allow_fallback", False))
    _ok(msg)
    return 0 if path is not None else 1


def cmd_migrate(args) -> int:
    raw_path = session.design_path()
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    migrated, changed = migrate_design(raw)
    if changed:
        session.save_design(migrated)
        _ok(f"Design migrado a schema 1.0. Copia previa guardada en {raw_path.parent / 'history'}")
    else:
        _ok("Design ya usa schema 1.0; no hubo cambios.")
    return 0


def cmd_project_new(args) -> int:
    path = projects.create_project(args.name, dim=args.dim, material=args.material, activate=True)
    _ok(f"Proyecto creado y activado: {path}")
    return 0


def cmd_project_list(args) -> int:
    _print_json(projects.list_projects())
    return 0


def cmd_project_open(args) -> int:
    _ok(f"Proyecto activo: {projects.set_active(args.name)}")
    return 0


def cmd_project_clone(args) -> int:
    _ok(f"Proyecto clonado y activado: {projects.clone_project(args.source, args.destination)}")
    return 0


def cmd_project_archive(args) -> int:
    _ok(f"Proyecto archivado: {projects.archive_project(args.name)}")
    return 0


def cmd_project_export(args) -> int:
    _ok(f"Paquete reproducible: {projects.export_project(args.name, args.out)}")
    return 0


def cmd_comsol_remote(args) -> int:
    from . import comsol_remote
    result = comsol_remote.certify(session.design_path(), args.out)
    _print_json(result)
    return 0 if result["compatible"] else 1


def cmd_target(args) -> int:
    features = json.loads(args.features) if args.features else {}
    tolerances = json.loads(args.tolerances) if args.tolerances else {}
    if not isinstance(features, dict) or not isinstance(tolerances, dict):
        raise ValueError("--features y --tolerances deben ser objetos JSON.")
    data = {"description": args.description or "", "features": features,
            "tolerances": tolerances}
    projects._atomic_json(session.artifact("target.json"), data)
    _ok(f"Objetivo estructurado guardado en {session.artifact('target.json')}")
    return 0


def cmd_assess(args) -> int:
    def items(raw):
        value = json.loads(raw) if raw else []
        if not isinstance(value, list):
            raise ValueError("matches/mismatches/suggestions deben ser listas JSON.")
        return value
    current_hash = design_hash(session.load_design())
    verification_path = session.artifact("verification.json")
    if not verification_path.exists():
        raise ValueError("Corre `qpot verify` antes de registrar la evaluación visual.")
    verified = json.loads(verification_path.read_text(encoding="utf-8"))
    if verified.get("design_hash") != current_hash:
        raise ValueError("El Design cambió desde el último verify; vuelve a verificar y mira el render nuevo.")
    data = {
        "render_inspected": bool(args.render_inspected), "score": float(args.score),
        "design_hash": current_hash,
        "matches": items(args.matches), "mismatches": items(args.mismatches),
        "suggestions": items(args.suggestions), "assumptions": items(args.assumptions),
    }
    if not 0 <= data["score"] <= 10:
        raise ValueError("--score debe estar entre 0 y 10.")
    projects._atomic_json(session.artifact("agent_assessment.json"), data)
    _ok(f"Evaluación visual guardada en {session.artifact('agent_assessment.json')}")
    return 0


def cmd_ui(args) -> int:
    """Abre el visualizador local Streamlit sobre la sesion actual."""
    import subprocess

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    if args.port is not None:
        cmd.extend(["--server.port", str(args.port)])
    return subprocess.call(cmd)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qpot",
        description="Herramientas para diseñar/ver/resolver/exportar potenciales cuánticos "
                    "(sin API). El Design vive en el proyecto activo del workspace.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("new", help="Crear una sesión nueva (Design en blanco)")
    sp.add_argument("--dim", type=int, choices=(1, 2), default=1)
    sp.add_argument("--material", default="GaAs")
    sp.add_argument("--L", type=float, default=None, help="Tamaño del dominio en nm")
    sp.add_argument("--N", type=int, default=None, help="Puntos de grilla")
    sp.set_defaults(func=cmd_new)

    sub.add_parser("state", help="Imprimir el Design actual (JSON)").set_defaults(func=cmd_state)
    sub.add_parser("describe", help="Contrato de parámetros del Design").set_defaults(func=cmd_describe)

    sp = sub.add_parser("render", help="Renderizar V a PNG (2D = superficie 3D + vista superior)")
    sp.add_argument("--out", default=None)
    sp.add_argument("--html", action="store_true",
                    help="También escribe un HTML 3D interactivo (plotly, sin servidor)")
    sp.add_argument("--open", action="store_true", help="Abre el resultado en el navegador")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("set", help="Cambiar un parámetro de una pieza")
    sp.add_argument("index", type=int)
    sp.add_argument("param")
    sp.add_argument("value")
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("add", help="Agregar una pieza")
    sp.add_argument("op", nargs="?", default=None, help="Nombre de la primitiva (perfil)")
    sp.add_argument("--args", default=None, help="Args JSON, p.ej. '{\"sigma\":5}'")
    sp.add_argument("--label", default=None)
    sp.add_argument("--json", default=None, help="Pieza completa como JSON (mask/where/etc.)")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("remove", help="Eliminar pieza por índice")
    sp.add_argument("index", type=int)
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("enable", help="Habilitar pieza")
    sp.add_argument("index", type=int)
    sp.set_defaults(func=cmd_enable)

    sp = sub.add_parser("disable", help="Deshabilitar pieza")
    sp.add_argument("index", type=int)
    sp.set_defaults(func=cmd_disable)

    sp = sub.add_parser("material", help="Cambiar material")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_material)

    sp = sub.add_parser("domain", help="Cambiar dominio (L nm / N puntos)")
    sp.add_argument("--L", type=float, default=None)
    sp.add_argument("--N", type=int, default=None)
    sp.set_defaults(func=cmd_domain)

    sp = sub.add_parser("from-preset", help="Cargar un preset del catálogo")
    sp.add_argument("name")
    sp.add_argument("--dim", type=int, choices=(1, 2), default=1)
    sp.add_argument("--params", default=None, help="Params JSON del preset")
    sp.set_defaults(func=cmd_from_preset)

    sp = sub.add_parser("set-image", help="Registrar imagen fuente (AFM/SEM/esquema)")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_set_image)

    sp = sub.add_parser("analyze-image",
                        help="Visión clásica: sugiere preset+params desde una foto (sin API)")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_analyze_image)

    sub.add_parser("clean", help="Limpiar artefactos de la sesión actual").set_defaults(func=cmd_clean)

    sp = sub.add_parser("param", help="Definir/actualizar un parámetro nombrado (bloque parameters)")
    sp.add_argument("name")
    sp.add_argument("value", nargs="?", default=None, help="Valor; omítelo para eliminar el parámetro")
    sp.set_defaults(func=cmd_param)

    sub.add_parser("validate", help="Validar el Design").set_defaults(func=cmd_validate)

    sp = sub.add_parser("solve", help="Resolver Schrödinger y guardar resultados")
    sp.add_argument("--n-states", type=int, default=6, dest="n_states")
    sp.set_defaults(func=cmd_solve)

    sp = sub.add_parser("verify", help="Loop: render + validar + resolver (señal objetiva)")
    sp.add_argument("--n-states", type=int, default=6, dest="n_states")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("sweep", help="Barrido paramétrico: E_n(parámetro) → sweep.csv/png")
    sp.add_argument("name", help="Parámetro nombrado (bloque parameters) o arg de pieza con --piece")
    sp.add_argument("--range", required=True, help="a:b:n  (p. ej. 0.1:0.5:9)")
    sp.add_argument("--piece", type=int, default=None, help="Índice de pieza (barre su arg `name`)")
    sp.add_argument("--n-states", type=int, default=4, dest="n_states")
    sp.set_defaults(func=cmd_sweep)

    sp = sub.add_parser("export", help="Exportar (csv/npz/m/mph/recipe)")
    sp.add_argument("--format", required=True, choices=session.EXPORT_FORMATS)
    sp.add_argument("--out", default=None)
    sp.add_argument("--n-states", type=int, default=6, dest="n_states")
    sp.add_argument("--allow-fallback", action="store_true",
                    help="Si falla .mph, generar receta/.m explícitamente")
    sp.set_defaults(func=cmd_export)

    sub.add_parser("migrate", help="Migrar el Design activo a schema 1.0 con respaldo").set_defaults(
        func=cmd_migrate)

    sp = sub.add_parser("project", help="Gestionar proyectos del workspace")
    project_sub = sp.add_subparsers(dest="project_cmd", required=True)
    pp = project_sub.add_parser("new", help="Crear y activar un proyecto")
    pp.add_argument("name")
    pp.add_argument("--dim", type=int, choices=(1, 2), default=1)
    pp.add_argument("--material", default="GaAs")
    pp.set_defaults(func=cmd_project_new)
    project_sub.add_parser("list", help="Listar proyectos").set_defaults(func=cmd_project_list)
    pp = project_sub.add_parser("open", help="Activar un proyecto")
    pp.add_argument("name")
    pp.set_defaults(func=cmd_project_open)
    pp = project_sub.add_parser("clone", help="Clonar y activar un proyecto")
    pp.add_argument("source")
    pp.add_argument("destination")
    pp.set_defaults(func=cmd_project_clone)
    pp = project_sub.add_parser("archive", help="Marcar un proyecto como archivado")
    pp.add_argument("name")
    pp.set_defaults(func=cmd_project_archive)
    pp = project_sub.add_parser("export", help="Empaquetar un proyecto reproducible")
    pp.add_argument("name")
    pp.add_argument("--out", default=None)
    pp.set_defaults(func=cmd_project_export)

    sp = sub.add_parser("comsol-remote-validate",
                        help="Certificar el Design activo en COMSOL 5.6 por SSH")
    sp.add_argument("--out", default="remote-comsol-results")
    sp.set_defaults(func=cmd_comsol_remote)

    sp = sub.add_parser("target", help="Definir objetivo estructurado del proyecto")
    sp.add_argument("--description", default="")
    sp.add_argument("--features", default="{}", help="Objeto JSON de features esperadas")
    sp.add_argument("--tolerances", default="{}", help="Objeto JSON de tolerancias")
    sp.set_defaults(func=cmd_target)

    sp = sub.add_parser("assess", help="Registrar evaluación visual del agente")
    sp.add_argument("--score", required=True, type=float)
    sp.add_argument("--render-inspected", action="store_true", required=True)
    sp.add_argument("--matches", default="[]")
    sp.add_argument("--mismatches", default="[]")
    sp.add_argument("--suggestions", default="[]")
    sp.add_argument("--assumptions", default="[]")
    sp.set_defaults(func=cmd_assess)

    sp = sub.add_parser("ui", help="Abrir visualizador local Streamlit (sin API)")
    sp.add_argument("--port", type=int, default=None)
    sp.set_defaults(func=cmd_ui)

    return p


def _force_utf8_output() -> None:
    """Evita 'charmap codec can't encode' en consolas Windows (cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
