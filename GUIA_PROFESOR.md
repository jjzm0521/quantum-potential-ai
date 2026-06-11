# Guía para el profesor — Quantum Potential AI

> Documento pensado para alguien que sabe **física cuántica de semiconductores** pero **no programa**.
> Si en algún momento ves una palabra rara, hay un glosario al final.

---

## 1. ¿Qué es esto y para qué sirve?

Es una **herramienta que convierte una descripción** (en lenguaje natural o una imagen AFM/SEM) **en una simulación cuántica completa**. Le dices, por ejemplo:

> *"Un pozo cuántico finito de GaAs de 30 nm con profundidad 250 meV"*

…y la herramienta:

1. **Interpreta** lo que escribiste
2. **Construye** el potencial matemáticamente, V(x) o V(x,y)
3. **Resuelve** la ecuación de Schrödinger sobre ese potencial
4. **Te muestra** los niveles de energía y las funciones de onda
5. **Te exporta** un archivo de COMSOL si lo quieres validar allá

En lugar de pasar horas montando manualmente la geometría y los parámetros en COMSOL para cada caso, describes el problema y la herramienta hace el primer borrador. Tú lo revisas, ajustas si hace falta, y si confirmas, lo simulas.

### ¿Por qué es útil?

- **Velocidad**: pasar de "tengo una idea" a "veo los eigenvalores" en segundos.
- **Exploración**: probar 20 variaciones de un sistema sin reconstruir nada.
- **Educativo**: los estudiantes ven cómo se traduce una descripción física a un modelo matemático y al final a una simulación.
- **Conectado a COMSOL**: cuando confíes en el resultado, puedes pedirle el archivo `.mph` o un script `.m` y refinar en COMSOL con confianza.

---

## 2. Instalación (la primera vez)

Necesitas Python 3.10 o más nuevo instalado. Si no lo tienes, descarga desde [python.org](https://www.python.org/downloads/).

Abre una terminal (PowerShell en Windows) y ejecuta estos comandos uno por uno:

```bash
cd ruta\donde\esta\Proyecto_cuantica
pip install -r requirements.txt
```

Esto instala todo lo que necesita la app (NumPy, SciPy, Streamlit para la interfaz, etc.). Tarda 1–2 minutos.

### Llave de API de Anthropic (para la parte de IA)

La parte de "describir con texto" o "subir imagen" usa Claude (la IA de Anthropic). Para activarla necesitas:

1. Crear una cuenta en [console.anthropic.com](https://console.anthropic.com)
2. Generar una API key (te dan unos créditos iniciales gratis)
3. Cuando abras la app, pegar la key en el sidebar izquierdo

**Sin la API key, igual puedes usar todos los modos manuales** (catálogo de potenciales con sliders). Solo no funciona el botón "Lanzar pipeline IA".

---

## 3. Cómo arrancar la app

Desde la terminal en la carpeta del proyecto:

```bash
python -m streamlit run app.py
```

Se abre en tu navegador en `http://localhost:8501`. Cuando termines, en la terminal apretas `Ctrl+C` para cerrarla.

---

## 4. La interfaz: 4 modos

En la parte superior derecha hay un selector con 4 opciones:

| Modo | Para qué sirve |
|---|---|
| **1D Catálogo** | Lista de potenciales 1D clásicos con sliders. Útil para enseñanza directa. |
| **1D Designer (IA)** | El que probablemente uses más. Describes en texto y la IA arma el potencial. |
| **2D Catálogo** | Lista de potenciales 2D (anillos, dots, etc.) con sliders. |
| **2D Designer (IA)** | Como el 1D pero para problemas planares (imágenes AFM, anillos, etc.). |

### 1D y 2D Catálogo (modo "tradicional")

Eliges un potencial del menú (pozo finito, oscilador armónico, doble pozo, anillo, etc.), ajustas sus parámetros con sliders, eliges material (GaAs, InAs, ...), presionas "Correr solver" y ves los resultados.

Útil para clases o cuando ya sabes exactamente qué quieres.

### 1D y 2D Designer (IA) — el modo nuevo

Aquí está la novedad:

1. En el cuadro de texto escribes una descripción
2. Click en "🚀 Lanzar pipeline IA"
3. La IA piensa unos segundos
4. Aparece el potencial dibujado + explicación de qué entendió + lista de "piezas" editables
5. Si algo no te gusta, mueves un slider o agregas una pieza
6. Click "Correr solver" → eigenvalores y funciones de onda

---

## 5. Cómo hablarle a la IA — qué decir y qué evitar

### ✅ Funciona muy bien

```
Pozo cuántico finito de GaAs de 30 nm de ancho con profundidad 250 meV.
```

```
Doble pozo gaussiano simétrico, sigma 5 nm cada uno, separados 30 nm.
```

```
Anillo cuántico InAs de radio 40 nm con un donador en el centro.
```

```
Heteroestructura GaAs/AlGaAs con campo eléctrico de 1 mV/nm en x.
```

Lo que la IA necesita para acertar:
- **Tipo de sistema** (pozo, anillo, doble pozo, barrera, etc.)
- **Tamaños** (nm) y **profundidades** (meV o eV)
- **Material** si lo sabes (GaAs, InAs, InGaAs, Si, GaN)
- **Particularidades**: campos, impurezas, asimetrías

### ⚠ Funciona regular

```
Hazme algo cuántico interesante.
```

(Demasiado vago — la IA tiene que adivinar todo)

```
Como en el paper de Smith 2019 figura 3.
```

(No sabe a qué paper te refieres — descríbeselo)

### ❌ No funciona

```
Calcula la energía de enlace de la impureza donadora con un láser de 1 THz.
```

Esto requiere módulos que **todavía no están implementados** (campos AC, regla de oro de Fermi). En el roadmap.

---

## 6. ¿Qué está haciendo la IA por dentro?

No es magia. Es un proceso transparente en 3 pasos. Lo importante: **cualquier paso puede equivocarse y tú lo puedes ver y corregir**.

### Paso 1 — El "Designer"

Lee tu descripción y la traduce a una **lista de piezas matemáticas**. Cada pieza es una primitiva del catálogo (gaussiana, anillo mexican-hat, barrera rectangular, super-elipse, etc.) con sus parámetros (centro, ancho, profundidad).

Esto es como construir el potencial con bloques de Lego: cada bloque es una función matemática conocida; el potencial final es la suma de todos los bloques.

La IA siempre te muestra:
- **Su análisis**: qué estructura cree que ve
- **El JSON** del Design: las piezas exactas que generó
- **Su auto-crítica**: tres cosas que cree que podrían estar mal en su propia respuesta

### Paso 2 — El "Verifier"

Otro paso de la IA toma el potencial generado, lo dibuja, y lo **compara con la descripción/imagen original**. Devuelve:
- Un puntaje de 0 a 10
- Qué cosas coinciden
- Qué cosas NO coinciden (específico)
- Sugerencias de cambios concretos

### Paso 3 — El "Refiner" (si hace falta)

Si el puntaje del verifier es bajo (< 7), un tercer paso toma el feedback y genera una versión corregida del Design. Esto se repite hasta máximo 3 veces o hasta llegar a puntaje ≥ 7.

### Por qué este diseño

Una sola pasada de IA se equivoca cada tanto y no hay forma de saberlo. Con 3 pasos separados (componer + verificar + refinar), cada error tiene una oportunidad de ser detectado. Y como todo el proceso es **visible para ti** (no es caja negra), tú decides si confías o ajustas a mano.

---

## 7. Interpretar los resultados

Después de "Correr solver" verás:

### Eigenvalores (niveles de energía)

```
E₀ = -262.57 meV
E₁ = -250.86 meV
E₂ = -165.07 meV
E₃ = -115.18 meV
```

- **Negativos** = estados **ligados** (atrapados en el pozo)
- **Positivos o cerca de cero** = estados **del continuo** o casi libres
- Si dos eigenvalores son muy cercanos (E₀ y E₁ con diferencia de pocos meV en doble pozo), eso es el clásico **desdoblamiento por tunneling**

### Funciones de onda

En 1D: aparecen como curvas a la altura del eigenvalor correspondiente (representación tipo libro de texto).

En 2D: aparecen como heatmaps de |ψ|² — más claro donde la probabilidad de encontrar al electrón es mayor.

### Validación analítica (cuando aplica)

Para potenciales con solución exacta (pozo infinito, oscilador armónico, Pöschl-Teller), la app muestra:

```
E₀:  numérico = 11.923 meV  |  analítico = 11.923 meV  |  error = <0.01%
E₁:  numérico = 35.767 meV  |  analítico = 35.770 meV  |  error = 0.008%
```

Esta es tu prueba de que el solver está correcto.

---

## 8. ¿Es confiable lo que sale?

Sí, **con dos verificaciones**:

### Verificación 1 — La hace la herramienta sola

Para potenciales clásicos compara contra la fórmula analítica. Errores típicos: **< 1%** con grilla normal, **< 0.01%** con grilla fina.

### Verificación 2 — La haces tú comparando con COMSOL

Para cualquier potencial, puedes:

1. Descargar el **script `.m`** generado por la app
2. Abrir MATLAB (con LiveLink for COMSOL activo)
3. Ejecutar el script → te arma el modelo en COMSOL automáticamente
4. Correr el solver de eigenvalores de COMSOL
5. Comparar los eigenvalores que da COMSOL con los que dio la app

Si coinciden (dentro del 1–2%, dependiendo de la grilla), confías en la app para ese tipo de sistema. **Si encuentras una discrepancia sistemática, eso es interesante y vale la pena investigar.**

### Niveles de confianza por componente

La IA reporta su propia confianza en 3 dimensiones:
- **Estructura cualitativa** (¿es un anillo o un pozo?) — casi siempre alta
- **Parámetros cuantitativos** (¿el ancho es 30 o 35 nm?) — media o baja según la información disponible
- **Material** (¿GaAs o InAs?) — alta si lo dijiste, media si lo dedujo

---

## 9. Exportar a COMSOL — paso a paso

Después de correr el solver, abajo aparecen botones de descarga:

| Botón | Qué descarga | Cuándo usarlo |
|---|---|---|
| 📄 CSV eigenvalores | Tabla de energías en CSV | Para tu informe o gráfico en Excel/Origin |
| 🔢 NumPy `.npz` | Arrays con funciones de onda | Si alguien va a hacer análisis en Python |
| 🔧 COMSOL `.m` | Script MATLAB de LiveLink | Para reconstruir en COMSOL |
| 📦 `.mph` directo | Archivo nativo de COMSOL | Para abrir en COMSOL con doble click |

**El más útil para ti probablemente es el `.mph`**:

1. Click "📦 Generar .mph"
2. Espera unos segundos (la app habla con COMSOL en segundo plano)
3. Descarga el archivo
4. Doble click → se abre en COMSOL con toda la geometría, el potencial definido y el estudio configurado
5. Ya puedes correr ahí, modificar lo que quieras, comparar con la versión Python

> [!TIP]
> **¿El potencial `V_pot` se ve plano en la gráfica de COMSOL?**
> Por defecto, COMSOL grafica las funciones analíticas en un rango gigante de `0 a 1 metro`. Aunque el exportador ya configura automáticamente los límites de graficación en base al tamaño `L` del dominio, si alguna vez ves el potencial plano, simplemente haz clic en la función analítica **`V_pot`** en COMSOL y en su panel de **Plot Parameters**, asegúrate de que los rangos de `x` (e `y`) estén configurados en el rango de los nanómetros (por ejemplo, de `-L/2` a `L/2` o de `-100e-9` a `100e-9` metros).

> *Nota: El `.mph` requiere haber instalado el paquete `MPh` con `pip install MPh`. Si no lo tienes, el botón sale grisado y siempre puedes usar el script `.m` con MATLAB.*

---

## 10. Ejemplo guiado completo

### Caso: pozo cuántico finito de GaAs

1. Abre la app: `python -m streamlit run app.py`
2. Pega tu `ANTHROPIC_API_KEY` en el sidebar
3. Selecciona modo **"1D Designer (IA)"**
4. En el cuadro de texto escribe:

   > *Pozo cuántico finito de GaAs de 30 nm de ancho con profundidad 250 meV. Quiero ver los estados ligados.*

5. Click **"🚀 Lanzar pipeline IA 1D (texto)"**
6. Espera ~20-30 segundos
7. Verás:
   - 🟢 **Score 9/10** (probablemente)
   - **Análisis del agente**: "Estructura observada: pozo cuántico cuadrado 1D estándar..."
   - **Design generado** con 1 pieza: `mask` con `interval` de centro 0 y largo 30 nm, valor -0.25 eV
   - El **plot del potencial** a la derecha
8. Click **"▶ Correr solver Schrödinger 1D"**
9. Aparecen los eigenvalores (algo así como):
   - E₀ = -224 meV
   - E₁ = -163 meV
   - E₂ = -75 meV
10. Las funciones de onda se dibujan dentro del pozo
11. Si quieres, click **"📦 Generar .mph"** y compara en COMSOL

---

## 11. Lo que NO hace todavía

Para no sorpresas, estas cosas **no están implementadas aún** pero están en el roadmap:

| Capacidad | Estado |
|---|---|
| Pozos / anillos arbitrarios | ✅ funciona |
| Impureza Coulomb | ✅ funciona |
| Campo eléctrico (Stark) | ✅ funciona como término lineal |
| Energía de enlace de impureza | ⚠ parcial (calcula el sistema, pero no el "binding" como diferencia con/sin impureza automáticamente) |
| Campo magnético uniforme | ❌ pendiente (módulo de fields) |
| Magnetización | ❌ pendiente (requiere barrido en B) |
| Polarizabilidad α | ❌ pendiente (requiere barrido en F) |
| Absorción óptica (regla de oro Fermi) | ❌ pendiente |
| Sistemas multi-electrón | ❌ pendiente (solo single-particle por ahora) |

**Cada uno se puede agregar como módulo nuevo sin romper lo existente**. Cuando los pidas, se agregan.

---

## 12. Solución de problemas comunes

### "La IA no entendió bien lo que quería"

- Reformula con más detalles (tamaños, profundidades, material)
- Activa el toggle del **"Verifier"** en el sidebar — fuerza que la IA revise su propia respuesta
- Si el score es bajo, deja al **Refiner** corregir (hasta 3 iteraciones)
- Si aun así no es lo que quieres, edita las piezas manualmente con los sliders

### "Los eigenvalores no convergen bien"

- Aumenta la **resolución de grilla** en el sidebar (de 512 a 1024 o 2048 en 1D; de 96 a 128 o 192 en 2D)
- Aumenta el **dominio** si las funciones de onda están "tocando" los bordes

### "El botón .mph está grisado"

- Necesitas instalar `MPh`: en terminal `pip install MPh`
- Y tener COMSOL instalado en la máquina
- Si no, usa el script `.m` con MATLAB+LiveLink

### "La IA me da un error"

- Revisa que la API key esté correcta y tenga créditos
- Si dice "JSON inválido", probablemente la IA tuvo un día malo — vuelve a lanzar
- Si persiste, mándame (a Juan José) el error exacto

---

## 13. Glosario rápido

| Término | Significado |
|---|---|
| **DSL** | Domain-Specific Language. Nuestro "lenguaje" interno para describir potenciales. Tú no lo escribes a mano. |
| **Primitiva** | Una función matemática básica (gaussiana, anillo, escalón). El potencial se arma sumando primitivas. |
| **Pieza** (`piece`) | Una primitiva con sus parámetros concretos. La unidad editable en la app. |
| **Design** | El JSON con la lista de piezas. La "fuente de verdad" del sistema. |
| **Pipeline IA** | El flujo Designer → Verifier → Refiner. |
| **Score** | Puntaje 0-10 que da el Verifier comparando lo generado con la descripción original. |
| **Eigenvalor** | Energía permitida del sistema. Lo que devuelve el solver de Schrödinger. |
| **Función de onda** (ψ) | Amplitud cuántica del electrón. Su cuadrado |ψ|² es la probabilidad de encontrarlo. |
| **Solver** | Programa que resuelve la ecuación de Schrödinger numéricamente. |
| **Diferencias finitas** | Método numérico para discretizar la derivada segunda. Lo que usa nuestro solver. |
| **eV / meV** | Unidades de energía. 1 eV = 1.602×10⁻¹⁹ J. 1 eV = 1000 meV. |
| **m\*** | Masa efectiva. En GaAs vale 0.067 veces la masa del electrón libre. |
| **MPh** | Librería de Python que se conecta a COMSOL — nos permite generar `.mph` sin abrir COMSOL ni MATLAB. |
| **LiveLink for MATLAB** | Producto de COMSOL que permite controlar COMSOL desde scripts de MATLAB. |
| **Pipeline de tunneling** | Fenómeno cuántico donde el electrón "pasa" por una barrera clásicamente prohibida. Se manifiesta como desdoblamiento de eigenvalores en sistemas con dobles pozos. |
| **Stark** | Efecto de un campo eléctrico sobre los niveles de energía. Se modela como un término lineal V = F·x. |

---

## 14. Contacto

Si encuentras un bug, una limitación, o quieres agregar una capacidad nueva:

- Apuntalo (qué hiciste, qué esperabas, qué pasó)
- Compártelo conmigo (Juan José)
- En la mayoría de casos se puede agregar/arreglar sin reescribir nada

---

*Esta herramienta está pensada para crecer contigo. Lo que hoy parece una "lista de potenciales fijos" es en realidad una base extensible: cada vez que te encuentres con un tipo de sistema nuevo, se puede agregar como primitiva y la IA aprende a usarla automáticamente.*
