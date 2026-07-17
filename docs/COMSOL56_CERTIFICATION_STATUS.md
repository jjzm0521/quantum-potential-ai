# Estado de certificación COMSOL 5.6

Ejecución real del 17 de julio de 2026 en el ASUS con COMSOL 5.6, dentro del entorno aislado
`C:\qpot-validation`. Resultado actual: **11/11 casos aprobados**.

| Caso | Estado | Error relativo máximo Python–COMSOL |
|---|---:|---:|
| Pozo finito 1D | Aprobado | 2.488% |
| Disco | Aprobado | 0.235% |
| Rectángulo | Aprobado | 1.298% |
| Elipse | Aprobado | 0.541% |
| Anillo | Aprobado | 0.426% |
| Superelipse | Aprobado | 1.248% |
| Composición booleana | Aprobado | 0.491% |
| Corona cicloidal | Aprobado | 0.773% |
| Dos zonas disjuntas | Aprobado | 1.581% |
| Barrido, R=16 nm | Aprobado | 0.435% |
| Barrido, R=22 nm | Aprobado | 0.288% |

La repetición completa terminó sin fallos. Las composiciones booleanas materializan cada
subdominio atómico antes de asignar `Ve`; la corona produce tres dominios con cobertura
`Vb / 0 / Vb`; y las superelipses y cicloides se construyen como polígonos paramétricos
cerrados, evitando cavidades o curvas que no particionan el dominio.

El disco, el anillo y las dos zonas disjuntas confirman específicamente la corrección de
estados degenerados del solver: Python conserva los pares esperados y COMSOL reproduce los
niveles dentro de la tolerancia definida.

Evidencia local regenerable: `remote-comsol-results/full-suite-fixed-20260717/` (ignorada por
Git por contener resultados y binarios `.mph`).
