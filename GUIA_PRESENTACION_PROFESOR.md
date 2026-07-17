# Guion de presentación — Quantum Potential AI 1.0

## Problema

En investigación, una geometría compleja suele aproximarse manualmente con elipses, curvas o
regiones. Si todo se reduce a una expresión opaca, se pierde la capacidad de preguntar qué
ocurre al cambiar un radio, achatamiento, número de lóbulos o barrera.

## Propuesta

El proyecto conserva esos grados de libertad en un Design paramétrico versionado. El mismo
Design alimenta el render, el solver, los barridos y COMSOL.

## Arquitectura para una diapositiva

```text
Texto/imagen → Agente Designer → Design 1.0 → Render + Verificación científica
                                      ├── Barridos
                                      ├── CSV/NPZ
                                      └── Receta/.m/.mph → COMSOL 5.6
```

## Evidencia que debe mostrarse

- `design.json` con parámetros tipados.
- Render del potencial y densidades de probabilidad.
- Reporte de residuos, malla, dominio, fuga y estados ligados.
- Historial inmutable de un `verify`.
- Barrido paramétrico.
- Receta COMSOL y, tras certificación, comparación de eigenvalores Python–COMSOL.

## Demostración en vivo desde un clon limpio

En Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
qpot --help
qpot demo install tres-picos
qpot verify --n-states 6
qpot ui --port 8509
```

Abrir `http://localhost:8509`. Si el demo ya existe, reemplazar la línea de instalación por:

```powershell
qpot project open demo-tres-picos
```

Orden sugerido dentro de la app:

1. Mostrar que el proyecto activo tiene `design.json`, objetivo e historial propios.
2. Señalar los parámetros `V_center_peak`, `V_central_trench` y sus unidades.
3. Ejecutar **Verificar** y enseñar convergencia, umbral de escape y seis estados ligados.
4. Abrir el render: tres máximos amarillos dentro de una sola cuenca morada conectada.
5. Comparar los eigenvalores con la evidencia COMSOL: error máximo de 0.224%.

La instalación completa puede tardar unos minutos en un equipo nuevo porque descarga SciPy,
Matplotlib y Streamlit. Para evitar depender de Internet durante la exposición, hacer este
paso antes de entrar al salón y repetir allí sólo `qpot verify` y `qpot ui --port 8509`.

## Qué demuestra el criterio geométrico

El comando `qpot geometry-study` mantiene constantes material, área confinada y relación de
aspecto para comparar una referencia detallada con figuras simples. En el caso incluido, la
elipse reproduce los niveles de la superelipse con un error máximo de 1.12%, por debajo de la
tolerancia del 3%; el disco llega a 5.29%. Por eso se recomienda la elipse para estudiar
niveles, pero se conserva la superelipse si el observable son separaciones finas.

## Respuestas breves

- **¿La IA calcula la física?** No. El agente interpreta la geometría; SciPy valida y resuelve.
- **¿Qué método numérico usa?** Diferencias finitas de segundo orden y `eigsh` para el
  Hamiltoniano simétrico disperso.
- **¿Cómo saben que converge?** Se compara con malla refinada y dominio ampliado, además de
  medir residuo, normalización, ortogonalidad y probabilidad en el borde.
- **¿El `.mph` siempre funciona?** Solo se declara compatible si COMSOL 5.6 lo abre, resuelve y
  coincide dentro de la tolerancia; de lo contrario la exportación falla explícitamente.
- **¿Por qué no usar GPU?** El backend de referencia usa matrices dispersas y ARPACK en CPU.
  Es portable y evita que una dependencia CUDA excluya los equipos del salón; para los casos
  docentes el coste de copiar a GPU puede superar la ganancia.
- **¿La imagen AFM determina dimensiones reales?** No si no tiene barra de escala ni perfil de
  altura. El demo reproduce la topología relativa; la calibración experimental debe aportar
  tamaño, material y offsets de banda.
