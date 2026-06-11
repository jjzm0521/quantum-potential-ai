# ⚛ Quantum Potential AI

Herramienta científica que va de **descripción de un potencial cuántico → simulación numérica** completa. Pensada como herramienta de investigación y enseñanza en mecánica cuántica de baja dimensión (puntos cuánticos, anillos, pozos, sistemas con impurezas y campos externos).

---

## 🎓 Guía de Explicación para el Profesor (Estructura y Metodología)

Si vas a presentar el proyecto a tu profesor, esta es la estructura física y computacional exacta que fundamenta la herramienta:

### 1. El Fundamento Físico: Ecuación de Schrödinger de Masa Efectiva
El sistema simula un **único electrón** confinado en una heteroestructura semiconductora de baja dimensión.
* **Hamiltoniano:**
  $$H = -\frac{\hbar^2}{2m^*} \nabla^2 + V(\mathbf{r})$$
  Donde $m^* = m_{eff} \cdot m_0$ es la masa efectiva del electrón en la banda de conducción del semiconductor (por ejemplo, $m_{eff} = 0.067$ para GaAs, $0.023$ para InAs).
* **Potencial $V(\mathbf{r})$:** Es una función tridimensional $V(x,y)$ o unidimensional $V(x)$ que representa el del perfil de conducción determinado por las uniones de materiales (heteroestructuras), la presencia de impurezas ionizadas (potencial Coulomb regularizado) o campos eléctricos aplicados (efecto Stark lineal).

### 2. El Solver Numérico (Diferencias Finitas)
En lugar de depender de simplificaciones analíticas, la app aproxima el Hamiltoniano usando el **método de diferencias finitas de segundo orden**:
* **Discretización:**
  $$\frac{d^2 \psi}{dx^2} \approx \frac{\psi_{i+1} - 2\psi_i + \psi_{i-1}}{\Delta x^2}$$
* **En 1D:** La matriz Hamiltoniana es **tridiagonal** y se diagonaliza directamente con solvers estándar de álgebra lineal.
* **En 2D:** El espacio se discretiza en una grilla rectangular de $N_x \times N_y$ puntos. El operador laplaciano $\nabla^2$ se convierte en una matriz de 5 puntos (stencil de 5 puntos). Como la matriz es extremadamente grande pero muy dispersa (sparse), usamos el **algoritmo de Arnoldi** (`scipy.sparse.linalg.eigs`) para extraer únicamente los $N$ niveles ligados de menor energía y sus correspondientes densidades de probabilidad $|\psi|^2$.

### 3. El Compositor de Potenciales (JSON DSL)
Para poder modelar cualquier forma compleja (ej. pozos acoplados, superelipses, rosetas de AFM), implementamos un **Lenguaje Específico de Dominio (DSL)** basado en JSON.
* El potencial final $V(\mathbf{r})$ es la **suma aditiva** de múltiples "piezas" paramétricas.
* Cada pieza tiene una **primitiva de región** (zona geométrica como elipses, rectángulos, anillos) y un **perfil de energía** (constantes, gaussianas, decaimientos). Esto permite modelar límites físicos exactos con un control numérico total.

### 4. Integración y Exportación a COMSOL
Para validar los cálculos de Python, la herramienta exporta el modelo directamente a COMSOL Multiphysics por tres vías:
1. **Archivo Nativo `.mph` Directo:** Compilado a través de la API de Java de COMSOL en Python (usando la librería `MPh`). Genera el archivo completo con geometría, malla fina, ecuaciones de la física (Coefficient Form PDE) y el estudio de eigenvalores preconfigurado.
2. **Script de MATLAB LiveLink (`.m`):** Un script de texto autogenerado que recrea el modelo al ejecutarse dentro de la consola LiveLink de COMSOL.
3. **El Recetario de Parámetros (Paso a Paso):** Un panel en la UI que desglosa la **traducción matemática** del diseño: le muestra al profesor exactamente qué parámetros globales crear en COMSOL, qué geometría dibujar y qué expresión analítica usar para $V_{pot}$ (con los límites de visualización `plotargs` ajustados a los nanómetros del pozo).

### 5. Robustez de la IA: El Flujo Multi-Agente
Cuando el profesor ingresa una descripción o una imagen AFM:
* **Designer Agent:** Propone el primer borrador de piezas JSON.
* **Verifier Agent (Multimodal):** Toma la imagen original, la compara visualmente con el render del potencial generado y califica de 0 a 10. Si el score es menor a 7, enumera las discrepancias específicas (`mismatches`) y sugiere correcciones.
* **Refiner Agent:** Toma las correcciones y redefine el diseño en un ciclo cerrado de hasta 3 iteraciones para asegurar que el potencial físico coincida con la AFM real.

---

## ¿Qué hace?

Tres modos de uso:

1. **1D Catálogo** — Pozos, barreras, oscilador armónico, doble pozo, Pöschl-Teller, Morse... con validación analítica.
2. **2D Catálogo** — Quantum dots, anillos, doble dot, triple dot, etc., con sliders y export.
3. **2D Designer (IA)** — Lo nuevo: **describe en lenguaje natural o sube una imagen AFM/SEM** y la IA compone el potencial como suma de primitivas paramétricas (gaussianas, super-elipses, rosetas, Coulomb...), con un loop de verificación visual que itera hasta que el render coincide con la imagen original.

Todo se resuelve numéricamente con un solver Schrödinger 2D/1D (diferencias finitas) y se exporta a:
- **CSV** de eigenvalores
- **NumPy `.npz`** con funciones de onda  
- **Script `.m` MATLAB/LiveLink** para COMSOL
- **Archivo `.mph`** directo a COMSOL (vía MPh — opcional)

---

## Arquitectura

```
                ┌──────────────────────────────────┐
                │   Potential Design (JSON DSL)    │  ← fuente de verdad
                │   + Material + Dominio           │
                └────────────────┬─────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
 ┌──────────────┐         ┌──────────────┐        ┌──────────────┐
 │ Solver Python│         │ Export .m    │        │ Export .mph  │
 │ (en la app)  │         │ (MATLAB)     │        │ (MPh directo)│
 └──────┬───────┘         └──────┬───────┘        └──────┬───────┘
        ▼                        ▼                       ▼
   Resultados                Script para             Archivo COMSOL
   inmediatos                MATLAB+COMSOL           abrible directo
   + CSV/npz
```

El **Design** es un dict JSON con una lista de "pieces". Cada pieza es una primitiva (gaussian, mexican_hat, coulomb, ...) o una operación compuesta (mask, where, clamp). Todas se suman para formar V(x,y).

### Pipeline de IA (modo Designer)

```
Input (imagen + texto)
    │
    ▼
[Designer Agent]  ← system prompt + few-shot + chain of thought + self-critique
    │
    ▼
Design JSON v1
    │
    ▼
[Validador numérico]  ← sanity checks sin IA (rangos físicos, NaN, etc.)
    │
    ▼
[Verifier Agent]  ← multimodal: compara render con imagen original
    │
    ▼  (si score < 7)
[Refiner Agent]  ← itera el Design corrigiendo mismatches
    │
    └──→ loop hasta score ≥ 7 o max 3 iters
    │
    ▼
Design final + score + trazabilidad completa
```

---

## Inicio rápido

**Windows** — doble click en `run.bat` (o desde cmd):
```cmd
run.bat
```

**Linux / macOS / Git Bash**:
```bash
./run.sh
```

Ambos scripts crean el venv, instalan dependencias en la primera corrida y abren
la app en http://localhost:8501. Para la IA, poné tu API key de Anthropic en `.env`:

```
ANTHROPIC_API_KEY=sk-ant-xxxx
```

## Instalación manual

```bash
cd Proyecto_cuantica
pip install -r requirements.txt
```

Para usar las funciones de IA, configurar la API key de Anthropic:

```bash
# Opción 1: archivo .env
echo "ANTHROPIC_API_KEY=sk-ant-xxxx" > .env

# Opción 2: variable de entorno

# Opción 3: ingresarla en el sidebar de la app
```

### Harness de agentes externos y parametrización

Los modos Designer incluyen un panel **Harness de agentes externos y cálculo local**.
Sirve para crear una tarea portable en `runs/agent_tasks/<task_id>/` para que un
agente externo describa y parametrice el potencial con las primitivas correctas:

- `request.json` — contexto estructurado para el agente
- `instructions.md` — instrucciones legibles para Codex/Claude/Antigravity
- `current_design.json` — Design actual
- `original.png/jpg/tiff` — imagen de referencia si se adjunta
- `render.png` — render actual si existe una corrida previa del verifier
- `result.json` — salida esperada para reimportar en la app

El objetivo principal es producir un `Design` correcto: geometría, piezas,
parámetros, unidades, supuestos y alternativas de parametrización. El solver
local queda como verificación secundaria, no como centro del flujo.

El panel permite adjuntar texto e imagen directamente al agente externo, sin
configurar `ANTHROPIC_API_KEY` o `GEMINI_API_KEY` en la app.

También puedes usarlo como CLI:

```bash
python -m ai.agent_harness list
python -m ai.agent_harness design-review <task_id>
python -m ai.agent_harness local-calc <task_id>
python -m ai.agent_harness validate-result <task_id>
```

Para registrar herramientas externas, define comandos por variable de entorno.
La app solo ejecuta comandos preconfigurados y requiere habilitación explícita:

```bash
AGENT_TOOL_CODEX='codex exec "{instructions_path}"'
AGENT_TOOL_CLAUDE='claude -p "@{instructions_path}"'
AGENT_TOOL_ANTIGRAVITY='antigravity-ide "{task_dir}"'
AGENT_HARNESS_ENABLE_RUN=1
```

Placeholders disponibles: `{task_dir}`, `{request_path}`, `{instructions_path}`,
`{current_design_path}` y `{result_path}`.

Si quieres usarlo con Codex:

1. Copia `.env.example` a `.env`.
2. Deja configurado `AGENT_TOOL_CODEX`.
3. Cambia `AGENT_HARNESS_ENABLE_RUN=1`.
4. En la app, abre el panel del harness, prepara una tarea y ejecuta Codex.

Para replicar este patrón en otro proyecto, conserva el mismo contrato:

- una carpeta de tarea por caso,
- `request.json` con objetivo, contexto y archivos de entrada,
- `instructions.md` para el agente,
- artefactos adjuntos junto a la tarea,
- `result.json` como única salida estructurada que la app importa y valida.

Para usar el export `.mph` directo a COMSOL (opcional):
```bash
pip install MPh
# Requiere COMSOL instalado en la máquina
```

---

## Uso

```bash
python -m streamlit run app.py
```

Se abre en `http://localhost:8501`. Tres modos en el toggle de arriba.

---

## Estructura del proyecto

```
Proyecto_cuantica/
├── app.py                       Interfaz Streamlit (3 modos)
│
├── core/                        Núcleo científico (independiente de UI)
│   ├── materials.py             GaAs, InAs, InGaAs, Si, GaN, libre
│   ├── potentials.py            Catálogo 2D legacy (quantum_dot, ring, etc.)
│   ├── potentials_1d.py         Catálogo 1D (10 potenciales)
│   ├── primitives.py            ▶ DSL: 8 regiones + 11 perfiles + ops
│   ├── safe_expr.py             ▶ Sandbox AST para raw_expr (whitelist)
│   ├── harnex.py                ▶ Header Harnex + validador pre-export COMSOL
│   ├── composer.py              ▶ Evalúa Design → V(x,y) array
│   ├── solver.py                Schrödinger 2D, diferencias finitas
│   ├── solver_1d.py             Schrödinger 1D, tridiagonal
│   ├── exporter.py              CSV, NumPy, COMSOL .m
│   └── exporter_mph.py          ▶ COMSOL .mph directo (MPh) — con puerta de validación
│
├── ai/                          Agentes IA
│   ├── vision_agent.py          (legacy, usado por modos catálogo)
│   ├── primitives_spec.py       ▶ doc auto-generada para los prompts
│   ├── prompts.py               ▶ system prompts + few-shot examples
│   ├── validators.py            ▶ validadores numéricos sin IA
│   ├── designer_agent.py        ▶ imagen/texto → Design JSON
│   ├── verifier_agent.py        ▶ comparación visual (multimodal)
│   ├── refiner_agent.py         ▶ refinador iterativo
│   ├── event_log.py             ▶ Event log JSONL append-only por run
│   └── pipeline.py              ▶ orquesta designer→verifier→refiner (con log)
│
├── examples/
│   └── ejemplo_python.py        Uso desde script Python
│
└── requirements.txt
```

---

## DSL de potenciales — primitivas

### Regiones (8) — devuelven máscara booleana

| Primitiva | Descripción |
|---|---|
| `disk` | Disco circular |
| `annulus` | Anillo entre dos radios |
| `rectangle` | Rectángulo (puede ir rotado) |
| `ellipse` | Elipse estándar |
| `super_ellipse` | `|x/a|ⁿ + |y/b|ⁿ ≤ 1` — n=2 elipse, n=4 cuadrado redondeado, n>>2 rectángulo, n<2 estrella |
| `rose` | Roseta `r ≤ R·|cos(kθ)|` — para puntos con pétalos |
| `polygon` | Polígono arbitrario |
| `half_plane` | Semi-plano respecto a un eje |

Combinables: `union`, `intersection`, `complement`.

### Perfiles de potencial (11) — devuelven V en eV

| Primitiva | Descripción |
|---|---|
| `constant` | V = c en todas partes |
| `gaussian` | Gaussiana 2D |
| `mexican_hat` | Sombrero mexicano (anillo cuántico) |
| `harmonic_2d` | Parabólico isótropo |
| `harmonic_anisotropic` | Parabólico anisótropo (ωx ≠ ωy) |
| `coulomb` | Impureza Coulomb regularizada |
| `linear` | Campo eléctrico uniforme V = F·x |
| `polynomial` | Polinomio bivariado arbitrario |
| `exp_decay` | Decaimiento exponencial radial |
| `poschl_teller` | -V₀/cosh²(αr) radial |
| `raw_expr` | Expresión numpy arbitraria — último recurso |

### Operaciones compuestas

| Op | Descripción |
|---|---|
| `mask` | `value` dentro de una región, 0 fuera |
| `where` | Pieza A dentro de región, pieza B fuera (piecewise puro) |
| `clamp` | Recorta V al rango [V_min, V_max] |
| `scale` | Multiplica una pieza por un factor |

---

## Schema del Design

```json
{
  "dim": 2,
  "material": "GaAs",
  "domain": {"L": 200.0, "N": 128},
  "pieces": [
    {
      "label": "anillo principal",
      "op": "mexican_hat",
      "args": {"center":[0,0], "r0":40, "depth":0.3}
    },
    {
      "label": "donador en el centro",
      "op": "coulomb",
      "args": {"center":[0,0], "charge":1.0, "eps_r":12.9, "regularization":1.5}
    },
    {
      "label": "campo eléctrico",
      "op": "linear",
      "args": {"slope":0.001, "axis":"x"}
    }
  ]
}
```

Las pieces se SUMAN entre sí. Cada una se puede deshabilitar con `"enabled": false`.

---

## Materiales

| Material | m* / mₑ | Eg (eV) | εᵣ |
|---|---|---|---|
| GaAs | 0.067 | 1.424 | 12.9 |
| InAs | 0.023 | 0.354 | 15.2 |
| InGaAs | 0.041 | 0.750 | 13.9 |
| Si | 0.191 | 1.120 | 11.7 |
| GaN | 0.200 | 3.400 | 9.0 |
| libre | 1.000 | — | 1.0 |

Fuente: Vurgaftman et al., J. Appl. Phys. 89, 5815 (2001).

---

## Calidad de la IA — cómo aseguramos que se equivoque lo menos posible

### En el lado del Designer (la "primera respuesta")

1. **System prompt estructurado** con: rol, escalas físicas típicas, primitivas disponibles, schema JSON, estrategia de descomposición en 8 pasos.
2. **Few-shot examples** — 3 casos completos resueltos con razonamiento explícito.
3. **Chain of thought obligatorio** — debe producir `<analysis>`, `<design>`, `<self_critique>` antes de cualquier output.
4. **Self-critique** — la IA enumera 3 cosas que podrían estar mal en su propia respuesta + confianza por componente (estructura / cuantitativos / material).

### En el lado de la Verificación (control de calidad)

5. **Validador numérico sin IA** — checa schema, parámetros en rango físico, NaN/Inf, dominio.
6. **Verifier multimodal** — recibe la imagen original + el render generado y devuelve:
   - `score 0-10`
   - lista de `matches` (lo que coincide)
   - lista de `mismatches` (lo que NO coincide, específico)
   - `suggestions` (cambios concretos)
7. **Loop de refinamiento** — si score < 7, el Refiner toma el feedback y modifica el Design preservando los matches y corrigiendo los mismatches. Máximo 3 iteraciones.

Toda esta trazabilidad se muestra en la UI: el usuario ve el razonamiento, el score, qué coincide, qué no, y puede revisar cada iteración.

---

## Validación del solver

Comparación contra soluciones analíticas:

| Sistema | Numérico | Analítico | Error |
|---|---|---|---|
| Pozo infinito 1D (E₁, L=40nm, GaAs) | 3.475 meV | 3.508 meV | 0.9% |
| Oscilador 1D (E₀, ω=0.0005) | 11.923 meV | 11.923 meV | <0.01% |
| Oscilador 2D, ratios E₀:E₁:E₂ | 1.00 : 2.00 : 2.99 | 1:2:3 | ✓ |

La pestaña *Validación con solución analítica* en la UI muestra estas comparaciones en vivo.

---

## Uso desde Python (sin UI)

```python
from core.composer import evaluate_design
from core.solver import solve, make_grid
from core.materials import get_material

design = {
  "dim": 2, "material": "GaAs",
  "domain": {"L":200,"N":96},
  "pieces": [
    {"op":"mexican_hat","args":{"center":[0,0],"r0":40,"depth":0.3}},
    {"op":"coulomb","args":{"center":[0,0],"charge":1.0,"eps_r":12.9,"regularization":1.5}},
  ],
}

x, y, X, Y = make_grid(200, 96)
V = evaluate_design(design, X, Y)
mat = get_material("GaAs")
res = solve(V, x, y, mat.m_eff, n_states=4)
print(res.energies_meV)
```

---

## Cómo extender

### Agregar una primitiva nueva

Editar `core/primitives.py`:

```python
def profile_mi_potencial(X, Y, center=(0.,0.), depth=0.3, sigma=10.):
    cx, cy = center
    r2 = (X-cx)**2 + (Y-cy)**2
    return -depth * np.exp(-r2/(2*sigma**2))  # ejemplo

PROFILE_PRIMITIVES["mi_potencial"] = PrimitiveSpec(
    name="mi_potencial", kind="profile", fn=profile_mi_potencial,
    args={"center":[0.0,0.0], "depth":0.3, "sigma":10.0},
    arg_units={"center":"nm","depth":"eV","sigma":"nm"},
    arg_help={"depth":"profundidad del pozo"},
    description="Mi potencial custom.",
)
```

La IA aprende a usarla automáticamente porque el prompt se genera desde el registry. El composer también lo recoge. La UI permite agregarla como pieza nueva.

### Agregar un material nuevo

Editar `core/materials.py` — añadir entrada al diccionario `MATERIALS`.

### Cambiar el solver

`core/solver.py` y `core/solver_1d.py` están aislados — se pueden reemplazar por FEniCS, shooting, Numerov, sin tocar la app.

---

## Harnex — ficha versionable del pozo

Cada Design puede llevar un bloque opcional `harnex` en la raíz que lo convierte
en una ficha auditable del componente. El header documenta identidad, propósito,
justificación de material/dominio y observables esperados en COMSOL.

```json
{
  "harnex": {
    "schema_version": "0.1",
    "id": "hz-ring-test",
    "purpose": "Anillo cuántico con donador central para barrido de B.",
    "material_justification": "GaAs por ωc accesible y eg conocido.",
    "domain_rationale": "L=200 nm con N=128 cubre estados ligados sin alias.",
    "expected_observables": ["eigenvalores", "densidad |ψ|²"],
    "owner": "lab-cuantica"
  },
  "dim": 2, "material": "GaAs",
  "domain": {"L": 200, "N": 128},
  "pieces": [...]
}
```

Helper en código:

```python
from core.harnex import default_harnex_header
header = default_harnex_header(
    well_id="hz-ring-test", purpose="Anillo con donador central",
    material="GaAs", domain_L_nm=200.0, domain_N=128,
    expected_observables=["eigenvalores", "densidad |ψ|²"],
)
design = {"harnex": header, "dim": 2, "material": "GaAs",
          "domain": {"L":200,"N":128}, "pieces": [...]}
```

### Puerta de validación pre-export a COMSOL

`export_mph()` corre `validate_for_comsol_export()` antes de iniciar MPh. Si el
Design no es exportable, lanza `ComsolExportError` con la lista de razones —
nunca se llega a abrir cliente COMSOL.

Chequeos duros:
- `dim==2`, pieces no vacío
- `domain.L ∈ [1, 5000] nm`, `domain.N ∈ [16, 2048]`
- material en `{GaAs, InAs, InGaAs, Si, GaN, libre}`
- `m_eff ∈ [1e-3, 10] m_e`, `n_states ∈ [1, 50]`
- header `harnex` (si está) bien formado
- el composer logra construir la expresión MATLAB

## Event log del pipeline IA

Cada corrida del pipeline produce `runs/{run_id}/` con:

- `events.jsonl` — eventos tipados append-only (`pipeline_start`, `designer_done`,
  `validator_done`, `verifier_done`, `refiner_done`, `pipeline_end`, etc.)
- `original.<ext>` — imagen original si la hubo
- `render_iter{n}.png` — render del verifier por iteración

Raíz configurable con `QUANTUM_RUNS_DIR`. `PipelineResult.run_id` y `run_dir`
exponen la ubicación. Inspección:

```python
from ai.event_log import list_runs, read_events
list_runs()                # resumen de runs
read_events("<run_id>")    # eventos completos del run
```

## Sandbox de `raw_expr`

La primitiva `raw_expr` ya no usa `eval()` desnudo. Se valida por AST contra una
whitelist estricta: solo literales numéricos, los nombres `x, y, r, theta, pi, e`
y un set fijo de funciones numpy. Bloquea acceso a atributos, subscripts,
lambdas, comprehensions, dunders y llamadas fuera de whitelist. Límites: 500
chars y profundidad AST 25.

## Limitaciones actuales

- Solo masa efectiva escalar (semiconductores isótropos).
- Campos magnéticos: se pueden agregar como pieza `polynomial` o `raw_expr` pero falta primitiva dedicada (Landau gauge).
- Absorción óptica / regla de oro de Fermi: pendiente como módulo `core/optical.py`.
- Polarizabilidad y magnetización: pendientes como módulo `core/observables.py` (sería barrido sobre F o B).
- Sin interacción electrón-electrón.
- Condiciones de frontera fijas: ψ=0 en los bordes del dominio.

Cada una se puede agregar como módulo nuevo sin reescribir el núcleo.

---

## Créditos

- Solver: método estándar de diferencias finitas para la ecuación de Schrödinger.
- IA: Claude (Anthropic), con pipeline multi-agente (designer + verifier + refiner).
- COMSOL via MPh (https://mph.readthedocs.io/) — opcional.
- Construido con Streamlit, NumPy, SciPy, Plotly, Matplotlib.
