# AGENTS.md — Guía para el agente (Claude Code / ChatGPT / Codex / Antigravity)

> **Contrato 1.0 (prevalece sobre referencias antiguas de este archivo):** el Design vive en
> el proyecto activo de `workspace/`, no en una sesión global. Empieza con `qpot project new`
> o `qpot project open`. Antes de diseñar, registra el objetivo con `qpot target`. Después de
> mirar `render.png`, registra la evaluación mediante `qpot assess --render-inspected`.
> `objective_ok` es un alias de `ready_to_export`: exige Design válido, solver convergido,
> traducción COMSOL válida y coincidencia explícita con el objetivo. Que `verify` termine no
> autoriza por sí solo a declarar el trabajo completo. Los Designs antiguos se migran con
> `qpot migrate` y `QPOT_SESSION_DIR` solo se conserva para compatibilidad/automatización.

> **Tú (el LLM) eres el cerebro de esta herramienta.** Este repositorio NO llama a ninguna
> API de pago: el "Designer", el "Verifier" y el "Refiner" que antes eran llamadas a un
> modelo ahora **los ejecutas tú** usando el CLI `qpot`. El estudiante te abre dentro del
> repo, te describe (o te sube una foto de) un potencial cuántico, y tú lo construyes,
> lo **ves**, lo verificas y lo exportas.

---

## 0. Qué es esto

Una herramienta para pasar de **"descripción de un potencial cuántico" → simulación
numérica completa** (Schrödinger 1D/2D por diferencias finitas) + exportación a COMSOL.

- El **Design** es el JSON del proyecto activo con piezas que se **suman** para formar
  V(x) o V(x,y). Es la **única fuente de verdad**. Coordenadas en **nm**, energías en **eV**.
- El **solver** y los **exportadores** ya existen y son confiables (`core/`). Tú no los
  reescribes: los manejas por el CLI.
- Para que el humano vea el potencial no hace falta servidor: `qpot render` da un PNG limpio y
  `qpot render --html` una superficie 3D interactiva (`potential.html`) que se abre con
  doble clic en cualquier navegador.

---

## 1. El loop que debes ejecutar (Designer → Verify → Refiner)

Este es el corazón del trabajo. Repítelo hasta que el potencial quede **bien descrito**:

1. **Designer** — A partir del texto/imagen del estudiante, construye el Design con el CLI
   (`qpot project new`, `qpot target`, `qpot from-preset`, `qpot add`, `qpot set`). Piensa primero la estructura
   dominante, la escala (nm/eV) y el material; luego elige primitivas (ver §4 y §5).
2. **Ver + Verify** — Corre `qpot verify`. Esto:
   - renderiza el potencial a `render.png` dentro del proyecto → **ábrelo/léelo y MÍRALO**;
   - valida el Design (esquema, física, numérico);
   - resuelve Schrödinger y reporta convergencia, eigenvalores y nº de estados ligados;
   - extrae **features cuantitativas** (`report.features`): nº de pozos, posiciones,
     profundidades, simetría (1D) / centroides, `ring_like`, `radial_symmetry` (2D).
     Úsalas para comparar con NÚMEROS contra el objetivo, no solo mirando el PNG;
   - contrasta contra teoría (`report.analytic_benchmark`): compara E1−E0 numérico
     con el modelo analítico que mejor aplique (ħω del fondo armónico o partícula en
     caja). Desviación pequeña = solver validado; grande = anarmonicidad, pozo finito
     o splitting túnel — **explícale al estudiante cuál es su caso**;
   - los issues `AVISO:` (p. ej. paredes de confinamiento muy altas) NO bloquean
     `objective_ok`: tú juzgas si son intencionales;
   - si hay imagen fuente (`qpot set-image`), te pide compararla con el render.
   Registra la calificación final con `qpot assess --score N --render-inspected ...`; solo
   entonces `target_match` puede aprobar la comparación visual.
3. **Refiner** — Si no coincide, ajusta piezas (`qpot set`, `qpot add`, `qpot remove`) y
   vuelve a `verify`. Conserva lo que ya estaba bien; corrige solo lo que falla.
4. Cuando coincida y `objective_ok` sea true → **exporta** (`qpot export`) y resume al
   estudiante qué hiciste, qué parámetros usó y su confianza.

> **Regla de oro:** nunca declares que un potencial está bien sin haber corrido `qpot verify`
> y **mirado** el PNG. "Ver para creer" cierra el loop sin costo de API.

### Subagentes (opcional, si tu cliente los soporta)
Claude Code (herramienta Task) y Antigravity permiten subagentes. Puedes delegar los roles:
un subagente **Designer** propone el Design, otro **Verifier** corre `qpot verify` y critica
el PNG, y un **Refiner** aplica correcciones. No es obligatorio: un solo agente puede hacer
todo el loop secuencialmente.

---

## 2. Comandos del CLI (`python -m qpot <cmd>`)

Todo opera sobre el Design del proyecto activo. Salida: las acciones imprimen un mensaje; las
consultas (`state`, `describe`, `solve`, `verify`, `validate`) imprimen JSON.

| Comando | Qué hace |
|---|---|
| `project new <nombre> --dim {1,2} [--material GaAs]` | Crea y activa un proyecto. |
| `target ...` · `assess ...` | Registra objetivo y evaluación visual verificable. |
| `state` | Imprime el Design actual (JSON). |
| `describe` | Contrato de parámetros: piezas, roles, tunables, supuestos. |
| `render [--html] [--open]` | Evalúa V → `render.png` (2D = superficie 3D + vista superior). **Léelo para VER el potencial.** `--html` añade una vista 3D interactiva; `--open` la abre en el navegador. |
| `set <idx> <param> <valor>` | Cambia un parámetro de una pieza (mover slider ≡). |
| `add <op> [--args '{json}'] [--label L]` | Agrega una pieza de perfil (gaussian, etc.). |
| `add --json '{pieza completa}'` | Agrega pieza compleja (mask/where con region/inner/outer). |
| `remove <idx>` · `enable <idx>` · `disable <idx>` | Gestiona piezas. |
| `material <nombre>` | GaAs / InAs / InGaAs / Si / GaN / libre. |
| `domain [--L nm] [--N pts]` | Ventana espacial y resolución. |
| `param <nombre> <valor>` | Define/actualiza un parámetro nombrado (bloque `parameters`). Sin valor → lo borra. |
| `from-preset <name> --dim {1,2} [--params '{json}']` | Carga un preset del catálogo. |
| `set-image <path>` | Registra imagen fuente (`session/source_image.*`). Léela tú. |
| `analyze-image <path>` | Visión clásica (sin API): detecta blobs/anillos/simetría y **sugiere** preset + params de arranque (JSON). Registra la imagen como fuente. Tú decides aplicarlo con `from-preset`. |
| `validate` | Valida el Design (sin resolver). |
| `solve [--n-states N]` | Resuelve; guarda `wavefunctions.png`, `eigenvalues.csv`, `result.json`. |
| `verify [--n-states N]` | **El loop**: render + validate + solve + chequeo de zonas solapadas (`zone_overlap`) → reporte objetivo. |
| `sweep <param> --range=a:b:n [--piece IDX] [--n-states N]` | **Barrido paramétrico** E_n(parámetro), la gráfica clásica de análisis (estilo COMSOL, pero local). Barre un parámetro nombrado o (con `--piece`) un arg de una pieza; guarda `sweep.csv` + `sweep.png`. Usa `--range=-0.5:-0.1:5` (con `=`) para valores negativos. No modifica el Design. |
| `export --format {csv,npz,m,mph,recipe} [--out path] [--n-states N]` | Exporta. |

`set` parsea el valor como JSON si puede: `qpot set 0 value -0.30`, `qpot set 1 sigma 8`,
`qpot set 0 center "[-15,0]"`, `qpot set 2 enabled false`.

### Presets disponibles
- **1D**: `finite_well`, `infinite_well`, `harmonic`, `double_well`, `barrier`, `step`,
  `morse`, `poschl_teller`, `triangular`, `gaussian_well`.
- **2D**: `quantum_dot`, `quantum_ring`, `double_dot`, `harmonic`, `triple_dot`.

### Geometría por parámetros (estilo COMSOL) — IMPORTANTE
El usuario modela como en COMSOL: **define regiones (geometría) por parámetros y les asigna un
potencial por región** (geometría y potencial separados). Para eso:

- **Curvas/regiones disponibles** (van dentro de `mask`/`where` y se combinan con
  `intersection`/`union`/`complement`): `disk`, `annulus`, `rectangle`, `ellipse`,
  `super_ellipse`, `rose`, **`epicycloid`** (flor de n lóbulos, args `R`, `n`),
  **`hypocycloid`** (estrella de n puntas, args `R`, `n`), `polygon`, `half_plane`.
- **Parámetros nombrados** (bloque `parameters`): define `R1`, `R2`, `n`, `Vb`… con
  `qpot param` y **referéncialos por nombre** en las args/value de las piezas (string).
  Así un solo cambio de `n` mueve todas las curvas (y en COMSOL queda como parámetro barrible).
- **Potencial por zona**: usa `where(region, inner, outer)` o varias `mask`.

**Caso canónico (corona cicloidal, el caso real del usuario):** electrón entre R1=12 nm
(hipocicloide interna) y R2=28 nm (epicicloide externa), n ciclos; V=228 meV salvo en el
canal entre las dos curvas donde V=0:
```
python -m qpot new --dim 2 --material GaAs
python -m qpot domain --L 100 --N 160
python -m qpot param R1 12
python -m qpot param R2 28
python -m qpot param n 7
python -m qpot param Vb 0.228
python -m qpot add --json "{\"op\":\"where\",\"label\":\"corona\",\"region\":{\"op\":\"intersection\",\"regions\":[{\"op\":\"epicycloid\",\"args\":{\"center\":[0,0],\"R\":\"R2\",\"n\":\"n\"}},{\"op\":\"complement\",\"region\":{\"op\":\"hypocycloid\",\"args\":{\"center\":[0,0],\"R\":\"R1\",\"n\":\"n\"}}}]},\"inner\":{\"op\":\"constant\",\"args\":{\"value\":0}},\"outer\":{\"op\":\"constant\",\"args\":{\"value\":\"Vb\"}}}"
python -m qpot verify
python -m qpot export --format recipe   # receta COMSOL: parámetros + Curvas Paramétricas + schr
```
En 2D, los tres exports generan **geometría por entidades** (Cuadrado + Curvas Paramétricas con
tus parámetros) + interfaz **Ecuación de Schrödinger** (Masa efectiva + Energía potencial de
electrón por dominio) + Estudio de Valor propio:
- `--format recipe` → receta markdown paso a paso (siempre funciona, sin dependencias).
- `--format m` → script LiveLink (necesita MATLAB+COMSOL para correrlo).
- `--format mph` → **archivo .mph nativo** que abre directo en COMSOL **sin MATLAB** (requiere
  `MPh` + COMSOL; ver versiones en requirements.txt). Si MPh no está, cae a la receta.

> ⚠ **Antes de tocar `core/exporter_mph.py` o el flujo del `.mph`, LEE
> [COMSOL_MPH.md](COMSOL_MPH.md).** Tiene la guía definitiva (matriz Java/MPh/jpype, estructura
> obligatoria, el reparto de potencial por dominio sin solapes, los gotchas de jpype y el
> checklist de verificación) para que el `.mph` NUNCA se genere mal.

---

## 3. Recetas rápidas

**Pozo finito 1D (texto):**
```
python -m qpot new --dim 1 --material GaAs
python -m qpot from-preset finite_well --dim 1 --params "{\"depth\":0.25,\"L\":30}"
python -m qpot verify
```

**Anillo cuántico 2D:**
```
python -m qpot new --dim 2 --material GaAs
python -m qpot from-preset quantum_ring --dim 2 --params "{\"depth\":0.3,\"r0\":40,\"width\":10}"
python -m qpot verify
```

**Doble pozo gaussiano desde cero (sin preset):**
```
python -m qpot new --dim 1 --material GaAs
python -m qpot add gaussian --args "{\"center\":-15,\"amplitude\":-0.2,\"sigma\":5}" --label "pozo izq"
python -m qpot add gaussian --args "{\"center\":15,\"amplitude\":-0.2,\"sigma\":5}"  --label "pozo der"
python -m qpot verify
```

**Pieza compleja (mask con región):**
```
python -m qpot add --json "{\"op\":\"mask\",\"region\":{\"op\":\"interval\",\"args\":{\"center\":0,\"length\":20}},\"value\":-0.3,\"label\":\"pozo\"}"
```

**Desde una foto (AFM/SEM/esquema):**
```
python -m qpot set-image ruta\a\foto.png   # luego LEE la imagen tú mismo
python -m qpot new --dim 2 --material GaAs
# ...construye piezas que reproduzcan lo que ves en la foto...
python -m qpot verify   # compara render.png contra la foto, e itera
```

---

## 4. Escalas físicas típicas (úsalas como sanity check)

- Punto cuántico GaAs/InAs: profundidad **50–500 meV**, tamaño **10–100 nm**.
- Anillo cuántico: radio **20–80 nm**, ancho **10–30 nm**.
- Pozo cuántico 1D (heteroestructura): profundidad **100–400 meV**, ancho **5–30 nm**.
- Barrera (tunneling): altura **100–500 meV**, ancho **1–10 nm**.
- Impureza donadora: Ry* ≈ 5.5 meV (GaAs), radio de Bohr a* ≈ 10 nm.
- Campos eléctricos: 1–100 kV/cm = **0.0001–0.01 eV/nm** (primitiva `linear`, efecto Stark).
- Oscilador armónico 1D: `omega_eV` ≈ **0.0002–0.001 eV/nm²**.
- Heteroestructura GaAs/AlGaAs: ΔEc ≈ **200–300 meV**.

Masas efectivas (m_e): GaAs 0.067 · InAs 0.023 · InGaAs 0.041 · Si 0.191 · GaN 0.200.

---

## 5. Estrategia para construir el Design (Designer)

1. **Identifica la estructura dominante**: ¿pozo? ¿anillo? ¿múltiples lóbulos? ¿qué simetría?
2. **Detalles geométricos (sobre todo en AFM)**: no asumas círculos perfectos. Formas
   alargadas → `ellipse` rotada; esquinas cuadradas redondeadas → `super_ellipse` (n≈2.5–4).
3. **Multi-bulto/acoplados**: define varias piezas desplazadas (centros por trigonometría si
   están inclinadas); el composer las suma.
4. **Escala**: estima nm y eV con §4.
5. **Primitiva principal** por componente; luego **correctoras** para asimetrías/defectos.
6. **Bordes duros** en 1D → `infinite_wall`. **Impureza** → `coulomb`. **Campo externo** →
   `linear`.
7. **Auto-crítica**: antes de cerrar, enumera 2-3 riesgos de tu parametrización.

El **esquema JSON del Design** y la **lista completa de primitivas** (1D y 2D, con sus args y
unidades) están en **[PRIMITIVES.md](PRIMITIVES.md)** — léelo antes de inventar piezas.

---

## 6. Cómo verificar (Verifier) — criterios

Mirando `render.png` (y, si existe, comparándolo con `source_image.*`):
1. **Estructura topológica**: mismos pozos/picos/anillos/lóbulos.
2. **Simetría**: ejes y centros coinciden.
3. **Proporciones** y **posiciones** de las features.
4. **Profundidades/alturas** relativas.
5. En 1D: número de pozos, posiciones, anchos, profundidades.

Escala sugerida para tu calificación: **9-10** casi idénticos · **7-8** ok con detalles
menores · **5-6** estructura principal ok, faltan detalles · **3-4** varios errores · **0-2**
fundamentalmente distinto. Reporta `matches`, `mismatches` y `suggestions` concretas (p.ej.
"subir sigma de pieza 1 a 8 nm"), y aplícalas en la siguiente iteración.

**Señales objetivas** que da `qpot verify` (no las ignores): `validation.issues` debe estar
vacío; `solver_valid` debe ser true; `solver.n_bound_states` > 0 si esperas estados
ligados (si es 0, el pozo es muy poco profundo/angosto o el dominio está mal).

---

## 7. Exportar a COMSOL / resultados

- `qpot export --format csv` → eigenvalores. `--format npz` → funciones de onda (NumPy).
- `qpot export --format m` → script MATLAB LiveLink. `--format recipe` → receta paso a paso.
- `qpot export --format mph` → `.mph` nativo estricto; si falla no sustituye el entregable.
  Usa `--allow-fallback` para solicitar explícitamente receta o `.m`.

---

## 8. Convenciones y límites

- **Unidades**: distancias en nm, energías en eV (el render muestra meV por legibilidad).
- **No** edites a mano archivos de `core/` para un caso puntual: cambia el Design.
- Si una primitiva no existe para lo que necesitas, usa `raw_expr` como último recurso, o
  propón al estudiante agregar una primitiva nueva en `core/primitives*.py`.
- La carpeta de sesión por defecto es `./session/` (configurable con `QPOT_SESSION_DIR`).
- El código que llamaba a la API quedó archivado en `legacy/` (no se usa en este flujo).
