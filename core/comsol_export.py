"""
Exportación a COMSOL **por geometría** + interfaz dedicada **Ecuación de Schrödinger (schr)**.

A diferencia de `composer.generate_comsol_recipe` (que escribía V como función analítica con
condicionales), este módulo reproduce el flujo real del usuario en COMSOL:

  - Geometría por entidades: un Cuadrado (dominio) + las regiones como entidades
    (Circle / Rectangle / Ellipse / Polygon nativas, o Curva Paramétrica con x(s),y(s) para
    súper-elipse / rosa / epicicloide / hipocicloide) + Formar unión.
  - Física con la interfaz **Ecuación de Schrödinger** (Masa efectiva + Energía potencial de
    electrón **por dominio** + Flujo cero + Valores iniciales).
  - Estudio de Valor propio (eigenvalues).

Los **parámetros nombrados** del Design (`parameters`) se emiten como parámetros globales de
COMSOL, así un barrido de, por ejemplo, `n` mueve todas las curvas a la vez.

`design_to_comsol_recipe` (markdown, principal) reproduce paso a paso ese árbol.
`design_to_comsol_m` (best-effort) genera el script LiveLink; las líneas específicas de la
interfaz `schr` van marcadas para verificar contra la versión de COMSOL del usuario.

Sólo 2D (el caso de regiones/curvas). Para 1D u opciones sin geometría, el llamador puede
seguir usando el camino analítico de `core.exporter`.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Parámetros y tokens
# ---------------------------------------------------------------------------

def _param_unit(name: str) -> str:
    """Unidad sugerida para un parámetro nombrado, según su nombre."""
    n = name.lower()
    if n in {"n", "k", "cycles", "ciclos", "nfoot", "nshape", "nexp"}:
        return ""           # adimensional
    if n.startswith("v") or any(t in n for t in ("depth", "amp", "height", "value", "pot", "barrier")):
        return "eV"
    if n in {"theta", "phi"} or "angle" in n or n.endswith("deg"):
        return "deg"
    # por defecto longitudes (R, R1, R2, L, center, a, b, sigma, ...)
    return "nm"


def _tok(arg: Any, unit: str = "nm") -> str:
    """Token COMSOL para un argumento: nombre de parámetro (string) o número con unidad."""
    if isinstance(arg, str):
        return arg                       # referencia a parámetro global
    if unit:
        return f"{arg}[{unit}]"
    return f"{arg}"


def _center_tokens(center: Any) -> tuple[str, str]:
    if isinstance(center, (list, tuple)) and len(center) == 2:
        return _tok(center[0]), _tok(center[1])
    return "0[nm]", "0[nm]"


def collect_parameters(design: dict) -> list[tuple[str, str, str]]:
    """Devuelve [(nombre, expr_con_unidad, descripción)] del bloque `parameters`."""
    rows = []
    for name, value in (design.get("parameters") or {}).items():
        unit = _param_unit(name)
        expr = f"{value}[{unit}]" if unit else f"{value}"
        rows.append((name, expr, f"parámetro '{name}'"))
    return rows


# ---------------------------------------------------------------------------
# Regiones → geometría
# ---------------------------------------------------------------------------

def _iter_atomic_regions(region: dict):
    """Recorre una región (posiblemente compuesta) y produce las regiones atómicas."""
    op = region.get("op")
    if op in ("intersection", "union"):
        for r in region.get("regions", []):
            yield from _iter_atomic_regions(r)
    elif op == "complement":
        yield from _iter_atomic_regions(region["region"])
    else:
        yield region


def _parametric_expr(op: str, args: dict) -> tuple[str, str]:
    """x(s), y(s) en función del parámetro 's' (∈[0,2π]) para curvas paramétricas.
    Usa nombres de parámetro o números (con unidad) según vengan en args."""
    cx, cy = _center_tokens(args.get("center", [0.0, 0.0]))
    ox = "" if cx in ("0[nm]", "0.0[nm]", "0") else f"+{cx}"
    oy = "" if cy in ("0[nm]", "0.0[nm]", "0") else f"+{cy}"

    if op in ("epicycloid", "hypocycloid"):
        R = _tok(args.get("R", 20.0))
        n = _tok(args.get("n", 5), unit="")
        r = f"({R}/{n})"
        if op == "hypocycloid":
            x = f"({R}-{r})*cos(s)+{r}*cos(({n}-1)*s){ox}"
            y = f"({R}-{r})*sin(s)-{r}*sin(({n}-1)*s){oy}"
        else:  # epicycloid
            x = f"({R}+{r})*cos(s)-{r}*cos(({n}+1)*s){ox}"
            y = f"({R}+{r})*sin(s)-{r}*sin(({n}+1)*s){oy}"
        return x, y

    if op == "super_ellipse":
        a = _tok(args.get("a", 15.0)); b = _tok(args.get("b", 15.0))
        ncoef = _tok(args.get("n", 4.0), unit="")
        # Superelipse paramétrica (signo·|cos|^(2/n)) para s∈[0,2π]
        x = f"{a}*sign(cos(s))*abs(cos(s))^(2/{ncoef}){ox}"
        y = f"{b}*sign(sin(s))*abs(sin(s))^(2/{ncoef}){oy}"
        return x, y

    if op == "rose":
        R = _tok(args.get("R", 20.0)); k = _tok(args.get("k", 4), unit="")
        x = f"{R}*abs(cos({k}*s))*cos(s){ox}"
        y = f"{R}*abs(cos({k}*s))*sin(s){oy}"
        return x, y

    raise ValueError(f"'{op}' no es una curva paramétrica")


def region_to_geometry(region: dict, tag: str) -> dict:
    """Describe cómo construir una región atómica como entidad de geometría COMSOL.

    Devuelve {tag, type, desc, recipe, m, params} donde:
      - type: tipo de feature COMSOL ('Circle','Square','Rectangle','Ellipse','Polygon',
              'ParametricCurve').
      - recipe: lista de líneas markdown (instrucciones para el usuario).
      - m: lista de líneas .m (LiveLink).
      - params: set de nombres de parámetro usados.
    """
    op = region.get("op")
    args = region.get("args", {}) if isinstance(region.get("args"), dict) else {}
    cx, cy = _center_tokens(args.get("center", [0.0, 0.0]))
    used = {v for v in _walk_param_names(region)}

    if op == "disk":
        R = _tok(args.get("radius", 10.0))
        return {
            "tag": tag, "type": "Circle", "desc": f"disco r={R}", "params": used,
            "recipe": [f"**Círculo** `{tag}`: Radio = `{R}`, Base = Centro, "
                       f"x = `{cx}`, y = `{cy}`."],
            "m": [f"c=geom.create('{tag}','Circle'); c.set('r','{R}'); "
                  f"c.set('base','center'); c.set('pos',{{'{cx}','{cy}'}});"],
        }
    if op == "rectangle":
        Lx = _tok(args.get("Lx", 20.0)); Ly = _tok(args.get("Ly", 20.0))
        rot = _tok(args.get("angle_deg", 0.0), unit="deg")
        return {
            "tag": tag, "type": "Rectangle", "desc": f"rectángulo {Lx}×{Ly}", "params": used,
            "recipe": [f"**Rectángulo** `{tag}`: Ancho = `{Lx}`, Alto = `{Ly}`, "
                       f"Base = Centro, x = `{cx}`, y = `{cy}`, Rotación = `{rot}`."],
            "m": [f"r=geom.create('{tag}','Rectangle'); r.set('size',{{'{Lx}','{Ly}'}}); "
                  f"r.set('base','center'); r.set('pos',{{'{cx}','{cy}'}}); r.set('rot','{rot}');"],
        }
    if op == "ellipse":
        a = _tok(args.get("a", 15.0)); b = _tok(args.get("b", 10.0))
        rot = _tok(args.get("angle_deg", 0.0), unit="deg")
        return {
            "tag": tag, "type": "Ellipse", "desc": f"elipse a={a}, b={b}", "params": used,
            "recipe": [f"**Elipse** `{tag}`: Semieje a = `{a}`, Semieje b = `{b}`, "
                       f"Base = Centro, x = `{cx}`, y = `{cy}`, Rotación = `{rot}`."],
            "m": [f"e=geom.create('{tag}','Ellipse'); e.set('semiaxes',{{'{a}','{b}'}}); "
                  f"e.set('base','center'); e.set('pos',{{'{cx}','{cy}'}}); e.set('rot','{rot}');"],
        }
    if op == "polygon":
        verts = args.get("vertices", region.get("vertices", []))
        pts = ", ".join(f"[{p[0]}, {p[1]}]" for p in verts)
        return {
            "tag": tag, "type": "Polygon", "desc": "polígono", "params": used,
            "recipe": [f"**Polígono** `{tag}`: vértices (nm) = {pts}."],
            "m": [f"% Polígono '{tag}': define la tabla de vértices (x,y) en metros."],
        }

    # Curvas paramétricas
    if op in ("epicycloid", "hypocycloid", "super_ellipse", "rose"):
        x_expr, y_expr = _parametric_expr(op, args)
        nombre = {"epicycloid": "epicicloide", "hypocycloid": "hipocicloide",
                  "super_ellipse": "súper-elipse", "rose": "rosa"}[op]
        return {
            "tag": tag, "type": "ParametricCurve", "desc": nombre, "params": used,
            "recipe": [
                f"**Curva Paramétrica** `{tag}` ({nombre}): Parámetro `s`, de `0` a `2*pi`.",
                f"  - Expresión x: `{x_expr}`",
                f"  - Expresión y: `{y_expr}`",
                f"  - (curva cerrada → luego 'Convertir a sólido' o queda como contorno de dominio).",
            ],
            "m": [
                f"pc=geom.create('{tag}','ParametricCurve');",
                f"pc.set('parname','s'); pc.set('parmax','2*pi');",
                f"pc.set('coord',{{'{x_expr}','{y_expr}'}});",
            ],
        }

    # Compuestas / desconocidas
    return {
        "tag": tag, "type": "?", "desc": f"región '{op}'", "params": used,
        "recipe": [f"_(región '{op}' no soportada como entidad; constrúyela manualmente)_"],
        "m": [f"% región '{op}' no soportada automáticamente."],
    }


def _walk_param_names(obj) -> set[str]:
    """Nombres de parámetro (strings) usados dentro de una estructura."""
    out: set[str] = set()
    if isinstance(obj, str):
        out.add(obj)
    elif isinstance(obj, list):
        for v in obj:
            out |= _walk_param_names(v)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("op", "axis", "side", "label"):
                continue
            out |= _walk_param_names(v)
    return out


# ---------------------------------------------------------------------------
# Potencial por dominio
# ---------------------------------------------------------------------------

def _region_desc(region: dict) -> str:
    """Descripción legible de una región (posiblemente compuesta) para el usuario."""
    op = region.get("op")
    if op == "intersection":
        return " ∩ ".join(_region_desc(r) for r in region.get("regions", []))
    if op == "union":
        return " ∪ ".join(_region_desc(r) for r in region.get("regions", []))
    if op == "complement":
        return f"fuera de ({_region_desc(region['region'])})"
    args = region.get("args", {})
    R = args.get("R", args.get("radius", args.get("a", "")))
    return f"{op}({R})" if R != "" else f"{op}"


def domain_potentials(design: dict) -> tuple[list[dict], list[str]]:
    """Extrae (asignaciones_por_dominio, términos_analíticos).

    asignaciones: [{region, region_desc, value, base}] para piezas mask/where con regiones.
    términos_analíticos: perfiles suaves (gaussian, etc.) que van como expresión adicional.
    """
    assignments: list[dict] = []
    analytic: list[str] = []
    for piece in design.get("pieces", []):
        if piece.get("enabled", True) is False:
            continue
        op = piece.get("op")
        if op == "where" and "region" in piece:
            inner = piece.get("inner", {}).get("args", {}).get("value", 0.0)
            outer = piece.get("outer", {}).get("args", {}).get("value", 0.0)
            assignments.append({
                "region": piece["region"],
                "region_desc": _region_desc(piece["region"]),
                "value": _tok(inner, "eV"), "base": _tok(outer, "eV"),
            })
        elif op == "mask" and "region" in piece:
            assignments.append({
                "region": piece["region"],
                "region_desc": _region_desc(piece["region"]),
                "value": _tok(piece.get("value", 0.0), "eV"), "base": "0[eV]",
            })
        else:
            analytic.append(op or "?")
    return assignments, analytic


def zone_overlap_issues(design: dict, N: int = 200) -> list[str]:
    """Detecta zonas (regiones de mask/where) que se SOLAPAN entre sí.

    En el .mph cada dominio sólo puede tener un `Ve`; zonas solapadas significan que en
    qpot los potenciales se SUMAN pero en COMSOL una zona ganaría (exclusividad) → el
    modelo no coincidiría. Devuelve lista de issues (vacía = zonas disjuntas, OK). 2D.
    """
    import numpy as np
    from .composer import resolve_params, _evaluate_region
    from .solver import make_grid

    d = resolve_params(design)
    if int(d.get("dim", 2)) != 2:
        return []
    L = float((d.get("domain") or {}).get("L", 200.0))
    _x, _y, X, Y = make_grid(L, N)
    zones: list[tuple[str, "np.ndarray"]] = []
    for p in d.get("pieces", []):
        if p.get("enabled", True) is False:
            continue
        if p.get("op") in ("mask", "where") and isinstance(p.get("region"), dict):
            try:
                m = np.asarray(_evaluate_region(p["region"], X, Y), dtype=bool)
            except Exception:
                continue
            zones.append((str(p.get("label", p.get("op"))), m))

    issues: list[str] = []
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            ov = int(np.count_nonzero(zones[i][1] & zones[j][1]))
            if ov > 0:
                frac = 100.0 * ov / zones[i][1].size
                issues.append(
                    f"Las zonas '{zones[i][0]}' y '{zones[j][0]}' se solapan "
                    f"({ov} celdas, {frac:.2f}% del dominio). En COMSOL una zona sólo puede "
                    f"tener un Ve; haz que sean disjuntas (usa complement/intersection).")
    return issues


# ---------------------------------------------------------------------------
# Receta markdown (entregable principal)
# ---------------------------------------------------------------------------

def design_to_comsol_recipe(design: dict, material: str = "GaAs", m_eff: float = 0.067,
                            n_states: int = 6) -> str:
    dim = int(design.get("dim", 2))
    L = float((design.get("domain") or {}).get("L", 200.0))
    params = collect_parameters(design)
    assignments, analytic = domain_potentials(design)

    # Recolectar curvas/regiones atómicas únicas
    atoms: list[tuple[str, dict]] = []
    seen = set()
    for a in assignments:
        for atom in _iter_atomic_regions(a["region"]):
            key = json.dumps(atom, sort_keys=True)
            if key not in seen:
                seen.add(key)
                atoms.append((f"reg{len(atoms)+1}", atom))

    geoms = [region_to_geometry(atom, tag) for tag, atom in atoms]
    used_params = set().union(*[g["params"] for g in geoms]) if geoms else set()

    md: list[str] = []
    md.append("# Receta COMSOL — geometría por regiones + Ecuación de Schrödinger\n")
    md.append(f"Material: **{material}** (m\\* = {m_eff} m₀) · Dominio cuadrado L = {L} nm · "
              f"{n_states} valores propios.\n")
    if dim != 2:
        md.append("> ⚠ Esta receta geométrica es para 2D. Para 1D usa el export analítico.\n")

    md.append("## 1) Parámetros globales (Definiciones → Parámetros)\n")
    if params:
        md.append("| Nombre | Expresión | Descripción |")
        md.append("|---|---|---|")
        for name, expr, desc in params:
            star = " ⭐" if name in used_params else ""
            md.append(f"| `{name}` | `{expr}` | {desc}{star} |")
    else:
        md.append("_(No hay bloque `parameters`. Recomendado: define R1, R2, n, Vb… para barrer.)_")
    md.append("")

    md.append("## 2) Geometría (Geometría → 2D)\n")
    md.append(f"1. **Cuadrado** `dom`: Lado = `{L}[nm]`, Base = Centro (es el dominio).")
    step = 2
    for g in geoms:
        for line in g["recipe"]:
            if line.startswith("  "):
                md.append(line)                      # sub-viñeta, sin numerar
            else:
                md.append(f"{step}. {line}")
                step += 1
    md.append(f"{step}. **Formar unión** (`fin`): genera los dominios delimitados por las curvas.")
    md.append("")

    md.append("## 3) Física — Ecuación de Schrödinger (schr)\n")
    md.append(f"1. Añade la interfaz **Ecuación de Schrödinger** sobre la geometría.")
    md.append(f"2. **Masa efectiva**: m\\* = `{m_eff}` (m₀).")
    md.append("3. **Energía potencial de electrón** por dominio "
              "(en cada nodo: *Fuente* = Definido por el usuario → `Ve`):")
    if assignments:
        for a in assignments:
            md.append(f"   - Nodo base sobre **todos** los dominios: `Ve` = `{a['base']}`.")
            md.append(f"   - Nodo extra seleccionando el dominio **{a['region_desc']}**: "
                      f"`Ve` = `{a['value']}`.")
    else:
        md.append("   - _(Sin piezas mask/where: asigna V por dominio según tu diseño.)_")
    if analytic:
        md.append(f"   - Términos suaves adicionales (perfiles {', '.join(analytic)}): "
                  f"agrégalos como expresión en la Energía potencial si los necesitas.")
    md.append("4. **Flujo cero** en los bordes externos (o Dirichlet ψ=0).")
    md.append("5. **Valores iniciales**: ψ = 0.")
    md.append("")

    md.append("## 4) Malla y estudio\n")
    md.append("1. Malla: Física controlada, tamaño Normal/Fina.")
    md.append(f"2. **Estudio → Valor propio**: nº de valores propios = `{n_states}`, buscar "
              f"alrededor de la energía de interés.")
    md.append("3. (Opcional) **Barrido paramétrico** sobre `n`, `R1`, `R2`… usando los parámetros.")
    md.append("")
    return "\n".join(md)


# ---------------------------------------------------------------------------
# Script .m (best-effort; verificar identificadores de 'schr')
# ---------------------------------------------------------------------------

def design_to_comsol_m(design: dict, material: str = "GaAs", m_eff: float = 0.067,
                       n_states: int = 6) -> str:
    L = float((design.get("domain") or {}).get("L", 200.0))
    params = collect_parameters(design)
    assignments, analytic = domain_potentials(design)

    atoms: list[tuple[str, dict]] = []
    seen = set()
    for a in assignments:
        for atom in _iter_atomic_regions(a["region"]):
            key = json.dumps(atom, sort_keys=True)
            if key not in seen:
                seen.add(key)
                atoms.append((f"reg{len(atoms)+1}", atom))
    geoms = [region_to_geometry(atom, tag) for tag, atom in atoms]

    lines: list[str] = []
    lines.append("% ============================================================")
    lines.append("% Quantum Potential — COMSOL LiveLink (geometría + Ecuación de Schrödinger)")
    lines.append("% Generado por qpot. Las líneas marcadas [VERIFICAR] dependen de tu versión")
    lines.append("% de COMSOL (interfaz 'Schrödinger Equation' del módulo de semiconductores).")
    lines.append("% ============================================================")
    lines.append("import com.comsol.model.*")
    lines.append("import com.comsol.model.util.*")
    lines.append("model = ModelUtil.create('QuantumPotential');")
    lines.append("")
    lines.append("% --- Parámetros globales ---")
    lines.append(f"model.param.set('m_eff','{m_eff}');")
    for name, expr, _ in params:
        lines.append(f"model.param.set('{name}','{expr}');")
    lines.append(f"model.param.set('Ldom','{L}[nm]');")
    lines.append("")
    lines.append("% --- Geometría 2D ---")
    lines.append("geom = model.geom.create('geom1', 2);")
    lines.append("sq=geom.create('dom','Square'); sq.set('size','Ldom'); sq.set('base','center');")
    for g in geoms:
        lines.append(f"% {g['desc']}")
        lines.extend(g["m"])
    lines.append("geom.run;   % equivale a 'Formar unión' (fin)")
    lines.append("")
    lines.append("% --- Física: Ecuación de Schrödinger (interfaz dedicada 'schr') ---")
    lines.append("schr = model.physics.create('schr','SchrodingerEquation','geom1');")
    lines.append("% Masa efectiva (Masa efectiva 1):")
    lines.append("schr.feature('meff1').set('meff','m_eff');   % [VERIFICAR nombre 'meff' en tu versión]")
    lines.append("% Energía potencial de electrón por dominio (Ve_src='userdef', Ve=<eV>):")
    lines.append("% 1) Base en TODOS los dominios:")
    lines.append("vb = schr.create('ve_base','ElectronPotentialEnergy',2);")
    lines.append("vb.selection.all;")
    lines.append("vb.set('Ve_src','userdef');")
    if assignments:
        lines.append(f"vb.set('Ve','{assignments[0]['base']}');")
        lines.append("% 2) Sobre-escritura por región (AJUSTA la selección de dominio en COMSOL):")
        for k, a in enumerate(assignments, 1):
            lines.append(f"ve{k} = schr.create('ve_{k}','ElectronPotentialEnergy',2);")
            lines.append(f"% ve{k}.selection.set([<nº de dominio: {a['region_desc']}>]);")
            lines.append(f"ve{k}.set('Ve_src','userdef');")
            lines.append(f"ve{k}.set('Ve','{a['value']}');")
    else:
        lines.append("vb.set('Ve','0[eV]');")
    if analytic:
        lines.append(f"% Términos suaves (perfiles {', '.join(analytic)}): añádelos a Ve como expresión.")
    lines.append("% Flujo cero (zf1) y Valores iniciales (init1) quedan por defecto.")
    lines.append("")
    lines.append("% --- Malla ---")
    lines.append("model.mesh.create('mesh1','geom1'); model.mesh('mesh1').autoMeshSize(3); model.mesh('mesh1').run;")
    lines.append("")
    lines.append("% --- Estudio de valor propio ---")
    lines.append("std = model.study.create('std1');")
    lines.append("eigv = std.create('eigv','Eigenvalue');")
    lines.append(f"eigv.set('neigs',{n_states});")
    lines.append("eigv.set('shift','0'); eigv.set('eigref','0.1');   % busca alrededor de 0.1 eV")
    lines.append("% model.study('std1').run;  % descomenta para resolver")
    lines.append("mphsave(model,'quantum_geometry.mph');")
    lines.append("")
    return "\n".join(lines)
