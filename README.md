# Quantum Potential AI 1.0

Herramienta docente y de investigación para convertir una descripción o imagen de un
potencial cuántico en un **Design paramétrico**, resolver Schrödinger 1D/2D y preparar un
modelo verificable para COMSOL 5.6.

El proyecto no llama una API de IA: el agente que el estudiante ya tiene abierto maneja el
CLI `qpot`. La app Streamlit y el agente trabajan sobre el mismo proyecto local.

## Instalación

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
qpot --help
```

Para desarrollo: `python -m pip install -e '.[dev]'`. Para generar `.mph` en una máquina
con COMSOL 5.6: `python -m pip install -e '.[comsol56]'`.

## Flujo recomendado

```bash
qpot project new anillo --dim 2 --material GaAs
qpot param R1 12
qpot param R2 28
qpot param n 7
qpot param Vb 0.228
# El agente agrega las regiones/piezas del Design.
qpot target --description "Corona cicloidal de siete lóbulos" \
  --features '{"ring_like":true,"n_wells":1}'
qpot verify
qpot assess --score 9 --render-inspected \
  --matches '["topología y escala coinciden"]'
qpot verify
qpot export --format recipe
qpot export --format mph
```

`verify` no confunde “el eigensolver terminó” con “el cálculo convergió”. Reporta residuos,
normalización, ortogonalidad, refinamiento de malla, expansión del dominio, fuga de borde y
estados ligados respecto al potencial exterior. `ready_to_export` solo es verdadero cuando
Design, solver, objetivo y traducción COMSOL están aprobados.

## Proyectos y archivos

Por defecto los trabajos viven en `workspace/<proyecto>/`, ignorado por Git:

```text
design.json                 fuente de verdad
target.json                 objetivo cuantitativo
agent_assessment.json       evaluación visual del agente
history/                    revisiones anteriores
runs/<id>/                  evidencia inmutable de cada verify
exports/                    entregables
```

Configura otra ubicación con `QPOT_WORKSPACE_DIR`. `QPOT_SESSION_DIR` se conserva para
automatizaciones antiguas. Una `session/design.json` anterior se importa como
`legacy-import` sin eliminar el original.

Comandos de proyecto: `new`, `list`, `open`, `clone`, `archive` y `export`. El último genera
un ZIP reproducible con Design, objetivo, evidencia y versiones.

## Design 1.0

Coordenadas en nm y energías en eV. Los parámetros contienen semántica explícita:

```json
{
  "schema_version": "1.0",
  "parameters": {
    "R1": {
      "value": 12,
      "unit": "nm",
      "dtype": "int",
      "kind": "length",
      "role": "radio interior",
      "min": 5,
      "max": 30
    }
  }
}
```

Las piezas siguen referenciando parámetros por nombre (`"R": "R1"`), por lo que los
Designs anteriores son compatibles. `qpot migrate` guarda una revisión y escribe schema 1.0.
Los presets exponen automáticamente sus escalares como parámetros nombrados.

## Solver

El Hamiltoniano de masa efectiva es

\[
H=-\frac{\hbar^2}{2m^*}\nabla^2+V.
\]

Se discretiza con diferencias finitas de segundo orden y se resuelve como matriz simétrica
dispersa mediante `scipy.sparse.linalg.eigsh`. El dominio numérico impone Dirichlet homogénea
en el exterior. Los resultados son una referencia local; la equivalencia con COMSOL debe
pasar la certificación descrita abajo.

## COMSOL 5.6

- `recipe`: receta Markdown auditable.
- `m`: script LiveLink.
- `mph`: archivo nativo estricto.

El export `.mph` no omite geometrías ni configuración crítica silenciosamente. Si una región
no tiene traducción garantizada, falla con un mensaje; `--allow-fallback` debe solicitarse
explícitamente para generar la receta alternativa.

La certificación remota usa claves SSH existentes y tres variables, documentadas en
`.env.example`. Luego:

```bash
qpot comsol-remote-validate --out remote-comsol-results
```

El ASUS debe ejecutar `scripts/comsol56_worker.py`. La certificación exige abrir, resolver y
comparar los eigenvalores: 1% para potenciales suaves y 3% para fronteras discontinuas.
Las versiones soportadas están en [COMPATIBILITY.md](COMPATIBILITY.md) y los detalles de la
API COMSOL en [COMSOL_MPH.md](COMSOL_MPH.md).

## App y agente

```bash
qpot ui
```

La app permite seleccionar proyectos, editar parámetros con unidades, registrar el objetivo,
ver historial y ejecutar el mismo pipeline que `qpot verify`. El agente debe seguir
[AGENTS.md](AGENTS.md), mirar `render.png`, registrar `qpot assess` y no declarar terminado un
caso hasta que `ready_to_export` sea verdadero.

## Calidad

```bash
python -m compileall -q qpot core ai app.py
pytest
```

La CI cubre Python 3.10–3.13. Las pruebas COMSOL se ejecutan remotamente porque requieren una
licencia e instalación real. El código histórico con API está aislado en `legacy/` y no se
instala.
