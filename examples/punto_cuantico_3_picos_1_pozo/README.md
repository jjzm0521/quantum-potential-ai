# Demo corregida: tres picos dentro de un único pozo

Este directorio es una evidencia reproducible y apta para presentar. No contiene credenciales,
historiales de trabajo ni binarios `.mph`; estos últimos se generan localmente y se validan por
su hash en [`evidence/manifest.json`](evidence/manifest.json).

## Interpretación

La imagen se representa como **un solo punto cuántico y una sola cuenca de confinamiento**.
Sobre esa cuenca aparecen tres máximos positivos del potencial: uno lateral izquierdo, uno
central y uno lateral derecho. El máximo central está rodeado por la zona más profunda de la
cuenca. No se modelan tres puntos ni tres pozos independientes.

Matemáticamente se separan:

1. El pozo común alargado, construido con dos gaussianas anchas muy solapadas. Su combinación
   es unimodal y forma una sola región negativa conectada.
2. Tres gaussianas positivas y estrechas que producen los picos observados.
3. Una corrección negativa alrededor del centro que forma el pozo que envuelve el pico central.

En las gráficas: amarillo significa pico positivo y morado significa pozo negativo.

## Parámetros

| Componente | Posición/ancho | Amplitud |
|---|---:|---:|
| Cuerpo del pozo | centros x=±8 nm, σ=20 nm | -60 meV cada base |
| Pico izquierdo | (-19, 3) nm, σ=6.5 nm | +100 meV |
| Pico central | (0, -1) nm, σ=4.5 nm | +240 meV |
| Pico derecho | (17, -3) nm, σ=7 nm | +110 meV |
| Pozo alrededor del centro | (0, -1) nm, σ=10 nm | -80 meV |

El potencial final va de -127.44 a +55.50 meV. El extractor encuentra una única región de
pozo conectada. La forma anular local detectada corresponde al pozo alrededor del máximo
central, no a varios pozos.

## Resultado científico

- Malla Python: 120×120.
- Seis estados ligados: -92.41, -89.15, -72.97, -70.06, -58.00 y -52.58 meV.
- Convergencia de malla y dominio aprobadas.
- Residuos del eigensolver inferiores a `1.7e-15`.
- Fuga de borde inferior a 0.1%.
- Evaluación visual 9.3/10 y `ready_to_export=true`.

## Barrido con criterio interpretable

Se barre la profundidad del pozo central `V_central_trench` desde -120 hasta -20 meV. Cuando
el pozo se hace menos profundo, todos los niveles suben y cambia su separación. El experimento
cuantifica específicamente cuánto influye la depresión que rodea el pico central.

```bash
# Desde la raíz del repositorio, prepara una copia de trabajo una sola vez:
mkdir -p workspace/demo-punto-cuantico-afm
cp examples/punto_cuantico_3_picos_1_pozo/{design,target,agent_assessment}.json \
  workspace/demo-punto-cuantico-afm/
qpot project open demo-punto-cuantico-afm
qpot verify --n-states 6
qpot sweep V_central_trench --range=-0.12:-0.02:6 --n-states 4
qpot ui
```

En Windows se pueden copiar esos tres JSON con el Explorador antes de ejecutar los mismos
comandos `qpot`. `verify` volverá a producir el render y toda la evidencia numérica.

## COMSOL 5.6

El mismo Design fue abierto, inspeccionado y resuelto en COMSOL 5.6. Los seis niveles coinciden
con Python y el error relativo máximo es **0.224%**, por debajo del criterio estricto de 1%.
La comparación completa, incluyendo la inspección de física, masa efectiva, potencial,
dominios y estudio, está en
[`evidence/comsol_comparison.json`](evidence/comsol_comparison.json).

## Archivos incluidos

- `design.json`: fuente paramétrica de verdad.
- `target.json` y `agent_assessment.json`: criterio y evaluación visual explícitos.
- `source_image.png`: imagen de referencia entregada para el ejercicio.
- `render.png`: potencial calculado; amarillo es positivo y morado negativo.
- `wavefunctions.png`: primeros seis autoestados.
- `sweep.png`: sensibilidad frente a la profundidad del pozo central.
- `estructura_3_picos_1_pozo.png`: esquema didáctico de la interpretación.
- `evidence/`: comparación COMSOL y hashes de trazabilidad.

## Limitación

La imagen no contiene barra de escala, alturas calibradas, material ni offset de banda. El
modelo reproduce la estructura relativa de tres picos y una cuenca común; para asignar valores
experimentales definitivos se necesita el perfil AFM calibrado.
