# Quantum Potential AI — Hoja de referencia

> ⚠ **El flujo cambió (junio 2026):** sin API key. Usa tu agente + el CLI `qpot`
> (`python -m qpot new/add/set/render/solve/verify/export`). Ver **[AGENTS.md](AGENTS.md)** y
> **[README.md](README.md)**. Lo de abajo describe la app vieja con API (archivada en `legacy/`).

> Para tener al lado del computador. Si necesitas más detalle, ver `GUIA_PROFESOR.md`.

---

## 🚀 Arrancar

```bash
cd Proyecto_cuantica
python -m streamlit run app.py
```

Abre `http://localhost:8501` en el navegador. `Ctrl+C` en la terminal para cerrar.

---

## 🎛 Los 4 modos

```
┌──────────────────┬──────────────────────────────────────┐
│ 1D Catálogo      │ Lista fija de potenciales 1D + sliders│
│ 1D Designer (IA) │ ★ Describes en texto → IA arma todo  │
│ 2D Catálogo      │ Lista fija de potenciales 2D + sliders│
│ 2D Designer (IA) │ ★ Imagen/texto → IA arma todo en 2D  │
└──────────────────┴──────────────────────────────────────┘
                              ★ = Modos nuevos con IA
```

---

## ✍ Cómo describirle a la IA

**Plantilla que funciona bien:**

```
[Tipo de sistema] de [material] de [tamaño] con [profundidad/altura].
[Cualquier particularidad: campo, impureza, asimetría]
```

**Ejemplos buenos:**

| Lo que quieres | Cómo decírselo |
|---|---|
| Pozo finito GaAs | "Pozo cuántico finito GaAs de 30 nm, profundidad 250 meV" |
| Doble pozo | "Doble pozo gaussiano simétrico, sigma 5 nm, separación 30 nm" |
| Anillo cuántico | "Anillo cuántico InAs radio 40 nm con donador en el centro" |
| Stark | "Pozo finito 30nm + campo eléctrico 1 mV/nm en x" |
| Heteroestructura | "GaAs/AlGaAs con barrera interna de 5 nm de ancho" |
| Quantum dot 2D | "Punto cuántico cuadrado redondeado 50×50 nm, profundidad 200 meV" |

---

## 🧠 Qué hace la IA por dentro

```
Tu descripción
     ↓
[Designer]   ──→  Genera el potencial como suma de "piezas"
     ↓
[Validator]  ──→  Chequea rangos físicos (sin IA)
     ↓
[Verifier]   ──→  Dibuja el potencial y lo compara con tu input
     ↓                              ↓
 Score 0-10                  Lista matches/mismatches
     ↓
 ¿Score ≥ 7?  ── NO ──→  [Refiner] corrige y vuelve a verificar
     ↓ SÍ                          (máximo 3 iteraciones)
 Listo
```

**Todo es visible.** Puedes expandir cada paso y ver el razonamiento.

---

## 📊 Interpretar resultados

| Lo que ves | Qué significa |
|---|---|
| E negativos | Estados ligados (atrapados en el pozo) |
| E positivos cerca de 0 | Estados delocalizados / continuo |
| Dos E muy cercanos | Tunneling (sistemas con doble pozo) |
| Función de onda con n nodos | n-ésimo estado excitado |
| Error < 1% vs analítico | Solver bien convergido |

---

## 📤 Exportar

| Botón | Para qué |
|---|---|
| 📄 CSV | Eigenvalores para Excel/Origin |
| 🔢 NumPy `.npz` | Análisis posterior en Python |
| 🔧 COMSOL `.m` | Script MATLAB+LiveLink para reconstruir en COMSOL |
| 📦 COMSOL `.mph` | Archivo directo de COMSOL (doble click → abre) |

---

## ⚠ Si algo sale mal

| Problema | Solución |
|---|---|
| IA entendió mal | Reformula con más detalle, activa Verifier+Refiner en sidebar |
| Eigenvalores raros | Aumenta resolución de grilla (sidebar) |
| ψ "tocan" los bordes | Aumenta dominio L (sidebar) |
| Botón .mph grisado | `pip install MPh` + tener COMSOL instalado |
| Error de API | Revisa key + créditos en console.anthropic.com |

---

## 🔬 Validación

Antes de creerle a un resultado, **siempre que puedas**:

1. **Comparar con solución analítica** (la app lo hace solo para pozo infinito, oscilador, Pöschl-Teller)
2. **Comparar con COMSOL**: descarga `.mph` o `.m`, corre allá, compara eigenvalores. Diferencia esperada: <2% con grilla normal.

---

## 📚 Unidades

| Cantidad | Unidad usada en la app |
|---|---|
| Longitud | nm |
| Energía | eV en inputs, meV en outputs |
| Masa efectiva m* | en unidades de mₑ (ej: GaAs = 0.067) |
| Campo eléctrico | eV/nm (ej: 0.001 = 10 kV/cm) |

---

## 🚧 Lo que aún NO hace (pendiente)

- Campo magnético uniforme
- Magnetización M = -∂E/∂B
- Polarizabilidad α = -∂²E/∂F²
- Absorción óptica (regla de oro Fermi)
- Energía de enlace como diferencia automática (con/sin impureza)
- Sistemas multi-electrón

Cuando pidas alguna de estas, se agrega como módulo nuevo.
