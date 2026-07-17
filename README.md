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
      "dtype": "float",
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

El backend estable es `scipy-arpack-cpu`: funciona en Windows, macOS y Linux sin depender de
una GPU. En 2D calcula internamente estados Ritz adicionales y usa una búsqueda determinista
para no perder niveles degenerados en discos, anillos y otras geometrías simétricas; la salida
continúa conteniendo exactamente los estados solicitados. Los operadores cinéticos dispersos
se reutilizan entre verificaciones y barridos con la misma malla, evitando reconstruir la parte
más estable del Hamiltoniano. El JSON de `solve`/`verify` informa `backend`,
`requested_states` y `computed_states` para que el coste sea auditable.

La versión 1.0 no activa GPU automáticamente. ARPACK trabaja principalmente en CPU y una copia
CPU→GPU puede empeorar los casos docentes pequeños; además, CUDA excluiría equipos sin NVIDIA y
Apple Silicon. La ruta prevista es un backend CUDA **opcional y explícito**, con el backend CPU
como referencia y comparación numérica obligatoria antes de aceptar sus resultados.

## Criterio de complejidad geométrica

`qpot geometry-study` compara simplificaciones contra un Design detallado sin modificar ningún
proyecto. Controla material, dimensión, área/longitud confinada y relación de aspecto; calcula
\(E_n\), separaciones, probabilidad dentro del punto y
\(S_E=|E_n^{cand}-E_n^{ref}|/|E_n^{ref}|\). Reporta por separado si una figura basta para
niveles individuales o si debe conservarse el detalle para reproducir *splittings*.

El ejemplo [disco–elipse–superelipse](examples/geometry_complexity_study/README.md) demuestra
el criterio: la elipse reproduce los niveles dentro de 1.12%, pero la superelipse sigue siendo
necesaria cuando interesan separaciones finas entre estados casi degenerados.

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
python scripts/comsol56_certification_suite.py --out remote-comsol-results/suite
```

El ASUS debe ejecutar `scripts/comsol56_worker.py`. El segundo comando recorre la matriz
obligatoria (1D, regiones, corona cicloidal, booleanas, zonas disjuntas y barrido). La
certificación inspecciona el árbol del modelo y exige abrir, resolver y comparar los
eigenvalores: 1% para potenciales suaves y 3% para fronteras discontinuas.
La matriz real más reciente aprobó **11/11 casos** en COMSOL 5.6.
Si SSH no está disponible, copia el repositorio al ASUS y ejecuta allí exactamente la misma
matriz con `python scripts/comsol56_certification_suite.py --local --out certification-local`.
Las versiones soportadas están en [COMPATIBILITY.md](COMPATIBILITY.md) y los detalles de la
API COMSOL en [COMSOL_MPH.md](COMSOL_MPH.md). El resultado de la última matriz real está en
[docs/COMSOL56_CERTIFICATION_STATUS.md](docs/COMSOL56_CERTIFICATION_STATUS.md).

## App y agente

```bash
qpot ui
```

La app permite seleccionar proyectos, editar parámetros con unidades, registrar el objetivo,
ver historial y ejecutar el mismo pipeline que `qpot verify`. El agente debe seguir
[AGENTS.md](AGENTS.md), mirar `render.png`, registrar `qpot assess` y no declarar terminado un
caso hasta que `ready_to_export` sea verdadero.

## Caso demostrativo para clase

El caso [tres picos dentro de un único pozo](examples/punto_cuantico_3_picos_1_pozo/README.md)
parte de una imagen AFM, conserva un solo confinamiento conectado y añade tres protuberancias
positivas. Incluye Design 1.0, objetivo, evaluación visual, render, funciones de onda, barrido
paramétrico y comparación real con COMSOL 5.6. El error máximo Python–COMSOL fue 0.224%.

Los archivos de trabajo y los `.mph` permanecen fuera de Git. En `examples/` solo se versiona
la evidencia compacta necesaria para entender y reproducir el caso.

## Calidad

```bash
python -m compileall -q qpot core ai app.py
pytest
```

La CI cubre Python 3.10–3.13. Las pruebas COMSOL se ejecutan remotamente porque requieren una
licencia e instalación real. El código histórico con API está aislado en `legacy/` y no se
instala.
