# Estado de certificación COMSOL 5.6

Ejecución real del 17 de julio de 2026 en el ASUS con COMSOL 5.6, dentro del entorno aislado
`C:\qpot-validation`. Resultado actual: **8/11 casos aprobados**.

| Caso | Estado | Error relativo máximo Python–COMSOL |
|---|---:|---:|
| Pozo finito 1D | Aprobado | 2.488% |
| Disco | Aprobado | 0.267% |
| Rectángulo | Aprobado | 1.327% |
| Elipse | Aprobado | 0.582% |
| Anillo | Aprobado | 0.438% |
| Dos zonas disjuntas | Aprobado | 1.599% |
| Barrido, R=16 nm | Aprobado | 0.472% |
| Barrido, R=22 nm | Aprobado | 0.312% |
| Superelipse | Bloqueado | COMSOL rechaza la malla por una cavidad inválida |
| Composición booleana | Bloqueado | un dominio queda sin asignación final de potencial |
| Corona cicloidal | Bloqueado | falta traducción COMSOL estricta de `where` |

Los tres bloqueos pendientes pertenecen al mallado/exportador COMSOL. Los eigenvalores del
solver Python sí se obtienen en esos casos. La versión 1.0 no debe declararse completamente
certificada hasta corregirlos y repetir la matriz completa.

El disco, el anillo y las dos zonas disjuntas confirman específicamente la corrección de
estados degenerados del solver: Python conserva los pares esperados y COMSOL reproduce los
niveles dentro de la tolerancia definida.
