# Matriz de compatibilidad

| Componente | Estado 1.0 |
|---|---|
| Python 3.10–3.13 | Probado por CI sin COMSOL |
| NumPy 1.26+ / SciPy 1.12+ | Soportado |
| COMSOL 5.6 | Certificado 11/11 con `MPh==1.2.3`, `jpype1==1.5.2` |
| COMSOL 6.x | No certificado en 1.0 |
| Windows 10/11 | Soportado por `run.bat` |
| macOS/Linux | Soportado para solver/app; COMSOL se valida remotamente |
| Solver CPU (`scipy-arpack-cpu`) | Backend de referencia, soportado en todas las plataformas anteriores |
| Solver GPU/CUDA | No habilitado en 1.0; aceleración opcional planificada, nunca requisito |

El export `.mph` solo se declara compatible para los casos que pasan apertura, solución y
comparación numérica mediante el runner remoto. La matriz obligatoria 1.0 pasó completa el
17 de julio de 2026. Las geometrías adicionales no traducibles se bloquean explícitamente.
