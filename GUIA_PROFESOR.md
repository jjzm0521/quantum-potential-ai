# Guía para el profesor — versión 1.0

Quantum Potential AI representa un potencial cuántico como una composición paramétrica de
geometrías y perfiles energéticos. El Design JSON es la fuente de verdad y separa la forma,
los parámetros, el material y el potencial asignado a cada zona.

## Qué demuestra el proyecto

1. Construcción reproducible de V(x) o V(x,y) desde texto, imagen o preset.
2. Solución local de la ecuación de Schrödinger de masa efectiva por diferencias finitas.
3. Verificación numérica por residuos, convergencia de malla/dominio y fuga de borde.
4. Barridos de parámetros geométricos o energéticos.
5. Traducción auditable a geometría y física de COMSOL 5.6.

El agente interpreta y refina la geometría; las comprobaciones científicas son código
determinista. La herramienta no usa una API de IA paga.

## Demostración sugerida

```bash
qpot project new demo-corona --dim 2 --material GaAs
# Construir la corona con R1, R2, n y Vb como parámetros.
qpot target --description "Corona cicloidal" --features '{"ring_like":true,"n_wells":1}'
qpot verify
qpot assess --score 9 --render-inspected --matches '["siete lóbulos","canal confinado"]'
qpot verify
qpot sweep R1 --range=10:16:4
qpot export --format recipe
```

En el reporte, explique la diferencia entre que el eigensolver termine y que el resultado
converja. Los estados ligados se comparan con el umbral exterior, no necesariamente con 0 eV.

## Límites declarados

- Es un modelo de un electrón y masa efectiva constante.
- La discretización local usa fronteras de Dirichlet en el dominio finito.
- Un `.mph` solo se considera certificado después de abrirse, resolverse y compararse con
  Python en COMSOL 5.6.
- Una geometría sin traducción estricta se bloquea; la receta manual continúa disponible.

Instalación, comandos y almacenamiento se documentan en [README.md](README.md).
