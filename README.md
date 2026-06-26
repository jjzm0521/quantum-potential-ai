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

### 5. El Flujo Multi-Agente (sin API de pago)
El "cerebro" es el LLM que el estudiante **ya tiene abierto** (Claude Code, ChatGPT, Codex,
Antigravity) trabajando sobre el repo. No se paga ninguna API. El mismo loop Designer →
Verifier → Refiner lo ejecuta ese agente usando el CLI `qpot`:
* **Designer:** a partir del texto/imagen, construye el `Design` JSON con `qpot add/set/from-preset`.
* **Verifier:** `qpot verify` renderiza el potencial a PNG (el agente lo **mira**), valida
  esquema/física y resuelve Schrödinger; si hay imagen fuente, el agente la compara con el render.
* **Refiner:** el agente ajusta las piezas y repite `verify` hasta que coincida con el objetivo.

Ver **[AGENTS.md](AGENTS.md)** para el manual del agente y **[PRIMITIVES.md](PRIMITIVES.md)**
para el esquema y las primitivas.

---

## ¿Qué hace?

Dos formas de uso, sobre la **misma sesión** (`session/design.json`):

1. **CLI `qpot` (lo maneja tu agente)** — Tu LLM (Claude Code / ChatGPT / Codex / Antigravity)
   construye el potencial desde texto o imagen, lo **renderiza para verlo**, lo verifica en un
   loop y lo exporta. Es el flujo principal, **sin API de pago**. Ver [AGENTS.md](AGENTS.md).
2. **Vista para el humano (sin servidor)** — `qpot render` da un PNG limpio y
   `qpot render --html` una **superficie 3D interactiva** (`session/potential.html`) que abres
   con doble clic. Sin API, sin Streamlit.

Hay un catálogo de presets clásicos (pozos, barreras, oscilador, doble pozo, anillos, dots…)
que el agente carga con `qpot from-preset`.

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

### Loop del agente (Designer → Verify → Refiner)

```
Input (texto + imagen)  →  el agente lo lee
    │
    ▼
[Designer]  qpot new / from-preset / add / set     → escribe session/design.json
    │
    ▼
[Verify]    qpot verify  → render.png (el agente lo MIRA) + validación + solver
    │
    ▼  (si no coincide o hay issues)
[Refiner]   qpot set / add / remove  → repite verify
    │
    └──→ loop hasta que el render coincida y objective_ok = true
    │
    ▼
qpot export  → COMSOL (.m/.mph/receta) / CSV / NumPy
```

El detalle del loop está en [AGENTS.md](AGENTS.md). En Claude Code, el comando `/potential`
lo arranca de una.

---

## Inicio rápido

**No se necesita ninguna API key.** El cerebro es tu propio agente.

1. Instala dependencias (una vez):
   ```bash
   pip install -r requirements.txt
   ```
2. Abre tu agente (Claude Code / ChatGPT / Codex / Antigravity) **dentro de esta carpeta** y
   pídele algo como *"abre el potencial: pozo finito de GaAs de 30 nm y 250 meV"*. Él usará el
   CLI `qpot` (ver [AGENTS.md](AGENTS.md)). O hazlo tú a mano:
   ```bash
   python -m qpot new --dim 1 --material GaAs
   python -m qpot from-preset finite_well --dim 1 --params "{\"depth\":0.25,\"L\":30}"
   python -m qpot verify     # genera session/render.png — ábrelo y míralo
   python -m qpot export --format m
   ```

### Ver el potencial (sin servidor)

```bash
python -m qpot render --html --open   # superficie 3D interactiva en el navegador
```

`render.png` (PNG limpio: en 2D, superficie 3D + vista superior) y `potential.html` (3D
rotable) quedan en `session/`. Para preparar el entorno de una: **Windows** → doble click en
`run.bat`; **Linux / macOS / Git Bash** → `./run.sh` (crean el venv, instalan deps y muestran
los comandos). El visor Streamlit antiguo quedó en `legacy/app.py`.

## Instalación manual

```bash
cd Proyecto_cuantica
pip install -r requirements.txt
```

No hace falta configurar ninguna API key para el flujo principal.

### El CLI `qpot` (la herramienta que maneja el agente)

Todos los comandos operan sobre `session/design.json`. Referencia completa en
[AGENTS.md](AGENTS.md); resumen:

```bash
python -m qpot new --dim {1,2} --material GaAs   # crear sesión
python -m qpot from-preset <name> --dim 1 --params "{...}"  # cargar preset
python -m qpot add gaussian --args "{\"center\":-15,\"amplitude\":-0.2,\"sigma\":5}"
python -m qpot set <idx> <param> <valor>         # mover un parámetro
python -m qpot render                            # → session/render.png (míralo)
python -m qpot solve --n-states 4                # eigenvalores + funciones de onda
python -m qpot verify                            # loop: render + validar + resolver
python -m qpot set-image foto.png                # registrar imagen fuente
python -m qpot export --format {csv,npz,m,mph,recipe}
```

La idea (estilo Text2CAD): tu agente lee el objetivo, construye el `Design`, lo **ve** en el
PNG, lo verifica e itera, y exporta a COMSOL. El solver local valida; el cerebro es tu LLM.

Para usar el export `.mph` directo a COMSOL (opcional):
```bash
pip install MPh
# Requiere COMSOL instalado en la máquina
```

---

## Uso

- **Con tu agente** (recomendado): ábrelo en esta carpeta y pídele el potencial; usará `qpot`.
- **Ver el resultado**: `python -m qpot render --html --open` (3D interactivo, sin servidor).

---

## Estructura del proyecto

```
Proyecto_cuantica/
├── AGENTS.md                    ★ Manual del agente (el flujo Designer→Verify→Refiner)
├── CLAUDE.md                    Pointer a AGENTS.md para Claude Code
├── PRIMITIVES.md                Esquema del Design + primitivas (generado)
├── .claude/commands/potential.md  Slash-command /potential (Claude Code)
│
├── qpot/                        ★ CLI sin API (lo maneja el agente)
│   ├── cli.py                   Subcomandos (new/add/set/render/solve/verify/export…)
│   ├── session.py              Sesión compartida (session/design.json) + solve/export
│   └── render.py               Render a PNG (matplotlib) + HTML 3D interactivo (plotly)
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
├── ai/                          Helpers sin API
│   ├── primitives_spec.py       ▶ doc de primitivas y esquema (fuente única)
│   ├── validators.py            ▶ validadores numéricos sin IA
│   ├── event_log.py             ▶ Event log JSONL append-only por run
│   └── agent_harness.py         ▶ contrato del Design / helpers de sesión
│
├── legacy/                      Archivado, no se usa en el flujo nuevo
│   ├── app.py                   visor Streamlit antiguo (con API)
│   ├── designer_agent.py · verifier_agent.py · refiner_agent.py
│   ├── vision_agent.py · pipeline.py · prompts.py
│   └── README.md
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

## Calidad — cómo el agente se equivoca lo menos posible

El agente (tu LLM) sigue una disciplina definida en [AGENTS.md](AGENTS.md):

### Al construir (Designer)
1. **Escalas físicas típicas** como sanity check (profundidades en meV, tamaños en nm).
2. **Estrategia de descomposición**: estructura dominante → geometría → escala → primitivas.
3. **Auto-crítica**: antes de cerrar, enumera 2-3 riesgos de su parametrización + confianza
   por componente (estructura / cuantitativos / material).

### Al verificar (`qpot verify`)
4. **Validador numérico sin IA** — checa schema, parámetros en rango físico, NaN/Inf, dominio.
5. **Render que el agente MIRA** — `session/render.png`; si hay imagen fuente, la compara.
6. **Solver como señal objetiva** — convergencia y nº de estados ligados.
7. **Loop de refinamiento** — el agente ajusta piezas y repite `verify` hasta que coincida.

Todo es inspeccionable: el Design vive en `session/design.json` y los renders/resultados en
`session/`, así que el estudiante puede revisar cada paso.

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

## Artefactos de la sesión

El CLI `qpot` trabaja sobre `session/` (configurable con `QPOT_SESSION_DIR`):

- `design.json` — el Design (fuente de verdad)
- `potential.html` — vista 3D interactiva (con `render --html`)
- `render.png` — render del potencial (el agente lo mira)
- `wavefunctions.png` — funciones de onda / |ψ|²
- `eigenvalues.csv`, `result.json` — resultados de `solve`
- `source_image.*` — imagen fuente registrada con `qpot set-image`

> El `event_log` JSONL (`ai/event_log.py`) y la carpeta `runs/` los usaba el pipeline
> histórico de `legacy/`; siguen disponibles para esa ruta.

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
- IA: el agente que ya usa el estudiante (Claude Code / ChatGPT / Codex / Antigravity),
  manejando el CLI `qpot` — sin API de pago embebida.
- COMSOL via MPh (https://mph.readthedocs.io/) — opcional.
- Construido con NumPy, SciPy, Matplotlib y Plotly (HTML 3D interactivo).
