# Cómo leer la pantalla de la app

> ⚠ **Actualización (junio 2026):** la interfaz principal ya no es esta app con API key. Ahora
> manejas el proyecto con tu agente (Claude Code / ChatGPT / Codex) y el CLI `qpot` — ver
> **[AGENTS.md](AGENTS.md)**. Para ver el potencial: `python -m qpot render --html --open`
> (superficie 3D interactiva en el navegador, sin servidor). Este texto describe la app vieja
> (Streamlit con API, archivada en `legacy/`) y se conserva como referencia.

Si abriste la app y no sabes qué es cada cosa, este documento es para ti.

---

## La pantalla por zonas

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⚛ Quantum Potential AI                       [Modo: 4 opciones]     │  ← Header
├──────────────────────────────┬───────────────────────────────────────┤
│                              │                                       │
│  PANEL IZQUIERDO             │   PANEL DERECHO                       │
│  (entrada / configuración)   │   (visualización en vivo)             │
│                              │                                       │
│  🤖 Generar con IA           │   📈 Plot del potencial               │
│   - Tabs: texto / imagen     │      (se actualiza en tiempo real)    │
│   - Botón "Lanzar pipeline"  │                                       │
│                              │   🟢 Resultado IA (si lanzaste)       │
│  📦 Material y dominio       │      - Score 0-10                     │
│   - Selector semiconductor   │      - Expandible: cada iteración     │
│   - Slider dominio L         │                                       │
│   - Slider resolución N      │   ⚡ Eigenvalores                     │
│                              │      E₀, E₁, E₂, E₃...                │
│  🧩 Pieces del Design        │                                       │
│   - Lista de piezas          │   📊 Funciones de onda                │
│   - Cada una editable        │      (plot tipo libro de texto en 1D, │
│   - Botón ➕ Agregar pieza   │       heatmaps |ψ|² en 2D)            │
│                              │                                       │
│  ▶ Botón Correr solver      │   📥 Botones de descarga              │
│                              │      CSV / NumPy / COMSOL .m / .mph   │
└──────────────────────────────┴───────────────────────────────────────┘
                ⬑ ⬑ ⬑ El SIDEBAR (lateral izquierdo) ⬑ ⬑ ⬑
                Configuración de API key, grilla, n_states, toggles
```

---

## Las "piezas" (`pieces`)

Cuando la IA genera un potencial (o cuando lo armas a mano), aparece una lista de **piezas** numeradas, cada una con un cuadrito tipo:

```
┌─────────────────────────────────────────────────────────┐
│ #1. mexican_hat — anillo cuántico        ☑ on    🗑    │
│   ▶ Editar parámetros                                   │
└─────────────────────────────────────────────────────────┘
```

- **#1, #2, ...** = número de orden (no afecta el resultado, solo organización)
- **mexican_hat** = la **primitiva** matemática (función del catálogo)
- **anillo cuántico** = etiqueta humana (la IA pone una sugerida; tú puedes ignorarla)
- **☑ on** = la pieza está activa (se incluye en el potencial). Si la desactivas, no se suma.
- **🗑** = botón para eliminar la pieza
- **▶ Editar parámetros** = expande sliders para ajustar centro, profundidad, ancho, etc.

**El potencial final = suma de todas las piezas activas.**

Esto es como un "constructor por capas":
- Primera pieza: el pozo principal (-300 meV)
- Segunda pieza: un donador (+atracción Coulomb)
- Tercera pieza: un campo eléctrico (+pendiente lineal)
- Total: suma = potencial completo

---

## El plot del potencial (panel derecho)

### En modo 1D

```
V (meV)
   ↑
 50│      ─ ─ ─ ─ E₃ = -50 meV ─ ─ ─ ─    ← Línea horizontal: eigenvalor
   │                ∼∼∼∼∼∼∼              ← Curva ondulada: función de onda
  0│ ─────╲     ╱─────       ─────       ← Curva blanca: V(x)
   │       ╲   ╱
-100│        ╲_╱
   │
   │
   └───────────────────────────────────→  x (nm)
        -40  -20   0   20   40
```

- **Curva blanca** = el potencial V(x) que estás simulando
- **Líneas horizontales punteadas** = eigenvalores (energías permitidas), una por estado
- **Ondulaciones de colores** = funciones de onda ψₙ(x), dibujadas a la altura de su eigenvalor (para visualización; la altura real de ψ no es energía)

### En modo 2D

- **Heatmap superior**: V(x,y) visto desde arriba. Azul = pozo, rojo = barrera, blanco = neutro.
- **Expandible "Vista 3D"**: lo mismo pero como superficie.
- **Heatmaps abajo** (después del solver): cada uno es |ψₙ(x,y)|² para un estado, brillante donde hay más probabilidad de encontrar al electrón.

---

## El "trace" de la IA

Después de lanzar el pipeline aparece algo así:

```
🟢 Resultado IA — score 8/10 (confianza: alta)

📋 Designer inicial    ·  score 8/10                       ▼
   Análisis del agente:
   "Estructura observada: pozo cuántico cuadrado 1D..."

   ✅ Coincide:                ⚠ No coincide:
   - Tipo: pozo finito         - Profundidad podría ser
   - Material: GaAs               250 en lugar de 230 meV
   - Ancho: 30 nm

   💡 Sugerencias:
   - Ajustar 'value' de pieza 1 a -0.25

   Render visto por el verificador:
   [imagen del potencial generado]

📋 Refinador iter 1    ·  score 9/10                       ▼
   Razonamiento del refinador:
   "Aplico la sugerencia: cambio value de -0.23 a -0.25..."
   ...

🔍 Auto-crítica del designer                               ▼
   "El dominio podría ser muy chico si el profe quiere ver..."
```

Cada bloque "📋" es **expandible**: click para abrir.

**Lectura típica:**
- 🟢 Score ≥ 7: confía en el resultado
- 🟡 Score 4-6: revisa los "mismatches" antes de confiar
- 🔴 Score < 4: la IA no entendió bien, reformula tu input

---

## Los sliders en el sidebar (lateral izquierdo)

```
┌──────────────────────────────────┐
│ ⚙ Configuración                  │
│                                  │
│ ANTHROPIC_API_KEY                │
│ [········································]│
│                                  │
│ Pipeline IA                      │
│ ☑ Activar verificador visual    │ ← Si lo desactivas,
│ ☑ Activar refinador iterativo   │   el pipeline es solo Designer
│                                  │
│ Grilla y solver                  │
│ Resolución 1D: [────●──] 1024    │ ← Más alto = más preciso
│ Dominio (nm):  [──●────] 120     │   pero más lento
│ Nº de estados: [──●────] 6       │
│                                  │
│ MPh (COMSOL directo): ✅         │ ← Si dice ❌, instalar MPh
│ MPh disponible.                  │
└──────────────────────────────────┘
```

**Resolución de grilla:**
- 1D: 512 (rápido) → 1024 (estándar) → 2048 (alta precisión)
- 2D: 64 (rápido) → 96 (estándar) → 128/192 (alta precisión)
- Reglar grilla más alta cuando los eigenvalores parecen no converger o las funciones de onda se ven "pixeladas"

**Dominio L:**
- Tiene que ser **más grande que tu potencial**
- Si los estados ligados se ven "tocando" los bordes del plot, aumenta L

**Nº de estados:**
- Cuántos eigenvalores calcular. Default 6. Para sistemas complejos puede subir hasta 12.

---

## Los botones de descarga

Después de correr el solver:

```
[📄 CSV eigenvalores]  [🔢 NumPy]  [🔧 COMSOL .m]  [📦 Generar .mph]
```

- **CSV**: solo las energías, una por línea, para meter en Excel.
- **NumPy** (.npz): archivo binario de Python con TODO (grilla, V, eigenvalores, funciones de onda). Para quien sepa Python y quiera analizar.
- **COMSOL .m**: script de MATLAB. Si tienes COMSOL + MATLAB + LiveLink, lo corres y arma el modelo solo.
- **Generar .mph**: archivo nativo de COMSOL. Doble click → abre el modelo en COMSOL directamente. (Solo disponible si tienes la librería MPh instalada.)

---

## Resumen visual de un caso típico

**Quieres:** un pozo finito GaAs de 30 nm.

**Pasos:**

```
1. Modo "1D Designer (IA)"
        ↓
2. Texto: "Pozo finito GaAs 30 nm 250 meV"
        ↓
3. Click "🚀 Lanzar pipeline IA"
        ↓
4. ESPERA ~20 seg → aparece resultado
        ↓
5. Revisa el score y el plot del potencial
        ↓
6. ¿Está bien? → Click "▶ Correr solver"
   ¿NO está bien? → Edita los sliders de las piezas o vuelve a lanzar pipeline
        ↓
7. Aparecen E₀, E₁, E₂... + funciones de onda
        ↓
8. Click "📦 Generar .mph" si quieres validar en COMSOL
```

**Tiempo total: ~1 minuto.**

Lo mismo a mano en COMSOL: armar geometría, definir material, escribir V(x), mallar, correr — fácil 15–20 minutos.

---

*Si después de leer esto algo sigue confuso, es bug de la documentación, no tuyo. Avísame y lo aclaro.*
