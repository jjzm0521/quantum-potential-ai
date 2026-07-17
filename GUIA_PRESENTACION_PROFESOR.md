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

## Respuestas breves

- **¿La IA calcula la física?** No. El agente interpreta la geometría; SciPy valida y resuelve.
- **¿Qué método numérico usa?** Diferencias finitas de segundo orden y `eigsh` para el
  Hamiltoniano simétrico disperso.
- **¿Cómo saben que converge?** Se compara con malla refinada y dominio ampliado, además de
  medir residuo, normalización, ortogonalidad y probabilidad en el borde.
- **¿El `.mph` siempre funciona?** Solo se declara compatible si COMSOL 5.6 lo abre, resuelve y
  coincide dentro de la tolerancia; de lo contrario la exportación falla explícitamente.
