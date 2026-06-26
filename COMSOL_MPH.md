# Cómo construir el `.mph` CORRECTAMENTE (guía definitiva)

> Esta guía recoge TODO lo aprendido para generar el `.mph` por **geometría + interfaz
> Ecuación de Schrödinger** sin errores. La implementación viva está en
> [`core/exporter_mph.py`](core/exporter_mph.py) (`export_mph_geometry`). **Si tocas ese
> archivo o regeneras el exporter, respeta estas reglas al pie de la letra.**
> Regla de oro: el `.mph` debe abrir y resolver en COMSOL **sin MATLAB**, con la geometría por
> entidades, el potencial **repartido por dominios sin solapes y cubriendo todo**, y los
> parámetros preservados para barridos.

---

## 0. Las 3 reglas que NUNCA se rompen

1. **Deshabilitar el nodo de potencial por defecto** de la interfaz Schrödinger (`ve1`). Su
   `Ve` por defecto es **armónico** y cubre todos los dominios → si queda activo, contamina todo.
2. **Reparto del potencial por dominio DISJUNTO y COMPLETO**: cada dominio en exactamente un
   nodo `ElectronPotentialEnergy`, sin zonas repetidas y sin dejar ninguna fuera.
3. **Conservar los parámetros nombrados** (`R1`, `R2`, `n`, `Vb`…) en `Ve` y en la geometría
   (no "quemar" números) para que los estudios/barridos funcionen en COMSOL.

---

## 1. Entorno: la matriz Java / MPh / jpype (causa #1 de fallos)

`MPh` usa `jpype` para hablar con la JVM de COMSOL. El error **"Java version too old. Java 9 or
later is required"** NO es de COMSOL: es de `jpype` (jpype ≥ 1.6 exige Java 11+). COMSOL trae su
propio Java:

| COMSOL | Java que trae | Versiones que funcionan |
|---|---|---|
| **5.6** | **Java 8** (openjdk 1.8) | `MPh==1.2.3` + `jpype1==1.5.2` ✅ (probado) |
| 6.x | Java 11+ | `MPh>=1.3` + `jpype1>=1.7` |

- Instalar (para COMSOL 5.6): `pip install "MPh==1.2.3" "jpype1==1.5.2"`.
- `JAVA_HOME`: el módulo apunta solo al JRE de COMSOL **si JAVA_HOME está vacío**. Si tienes un
  Java viejo en `JAVA_HOME`, jpype lo usará → falla. Déjalo vacío o apúntalo al JRE de COMSOL
  (`C:\Program Files\COMSOL\COMSOL56\Multiphysics\java\win64\jre`).
- **Higiene de procesos**: si ves *"The client is not connected to a server"* al INICIO, hay un
  `comsol` / `comsolmphserver` / `java` huérfano de una corrida previa. Mátalos y reintenta:
  `Get-Process java,javaw,comsol,comsolmphserver | Stop-Process -Force`.

---

## 2. Estructura obligatoria del modelo (orden importa)

1. **Parámetros globales** (`model.parameter(nombre, expr)`): `m_eff`, `Ldom`, y todos los del
   bloque `parameters` con unidad (`R1 = 16[nm]`, `Vb = 0.27[eV]`, `n = 7`).
2. **Geometría 2D** (`model.create('geometries/geom1', 2)`):
   - `Square` dominio: `.property('size','Ldom')`, `.property('base','center')`.
   - Cada región como entidad:
     - `Circle`: `.property('r', R)`, `.property('pos',[cx,cy])`, `.property('base','center')`.
     - `Ellipse`: `.property('semiaxes',[a,b])`, `pos`, `base`.
     - `Rectangle`: `.property('size',[Lx,Ly])`, `pos`, `base`.
     - `ParametricCurve` (epicicloide/hipocicloide/súper-elipse/rosa):
       `.property('parname','s')`, `.property('parmax','2*pi')`,
       `.property('coord',[x_expr, y_expr])` — las expresiones usan los **parámetros** (R2, n…).
   - `geom.run()` ⟵ esto hace **Formar unión** (genera los dominios).
3. **Física = interfaz dedicada** `model.create('physics/schr','SchrodingerEquation','geom1')`:
   - **Masa efectiva**: `phys.java.feature('meff1').set('meff', 'm_eff')`.
   - **Deshabilitar el potencial por defecto**: `phys.java.feature('ve1').active(False)`.
   - **Energía potencial por dominio** (ver §3): nodos `ElectronPotentialEnergy` con
     `Ve_src='userdef'` y `Ve=<expr>`.
   - Flujo cero (`zf1`) y Valores iniciales (`init1`) quedan por defecto.
4. **Malla**: `model.create('meshes/mesh1','geom1')`, `autoMeshSize(3)`, `run`.
5. **Estudio de valor propio**: `study.create('Eigenvalue', name='eigv')`,
   `.property('neigs', N)`, `.java.set('shift','0')`, `.java.set('eigref','0.1')`.
6. **Guardar**: `model.save(path)`; luego `client.disconnect()` **envuelto en try/except**
   (en modo stand-alone lanza "client not connected" PERO el `.mph` ya quedó guardado).

---

## 3. El reparto del potencial por dominio (el error a NUNCA cometer)

Síntoma del error: "un par de regiones quedaron definidas para todos los elementos y todo cayó
en el potencial por defecto (armónico); `ve_base` se solapaba con la región".

Procedimiento correcto:

1. **Deshabilita `ve1`** (el default armónico). Sin esto, nada más importa.
2. **Calcula zonas por puntos interiores reales** (robusto a la numeración de dominios de
   COMSOL, que no se conoce al generar el script):
   - Evalúa la **máscara** de cada región sobre una grilla.
   - Por cada **componente conexa**, toma el punto más profundo (máx. `distance_transform_edt`).
   - Crea una **Ball selection** de dominios en ese punto:
     `entitydim = JInt(2)`, `posx/posy = '<x>[nm]'`, `r = '0.5[nm]'`, `condition = 'intersects'`.
   - Si una zona tiene varias componentes → varias Balls + una **Union selection**.
3. **Partición según el tipo de pieza**:
   - `where(region, inner, outer)` → **dos** nodos disjuntos: `región` = `inner`, y
     **complemento de la región** = `outer`. (Corona: canal = inner; las dos barreras = outer.)
   - `mask(region, value)` → `región` = `value`; complemento = `0`.
   - Varias regiones → base en todo + overrides (COMSOL resuelve por **exclusividad**: el nodo
     posterior se queda con sus dominios), con el default igualmente deshabilitado.
   - Sin regiones (perfil analítico, p. ej. `raw_expr`) → un nodo con `Ve` = la expresión.
4. **Asignar la selección**: `ve.java.selection().named(<TAG REAL>)`. El tag real se obtiene con
   `nodo.java.tag()`, **no** con el nombre del path que pusiste al crear (ese no es el tag).

---

## 4. Gotchas de MPh / jpype (cada uno costó un intento)

- **Enteros ambiguos**: `feature.set('entitydim', 2)` lanza *"Ambiguous overloads (boolean/int)"*.
  Solución: `from jpype import JInt` y pasar `JInt(2)`.
- **`.named()` con tag inexistente** → *"Unknown selection"*. Usa `nodo.java.tag()` (el tag que
  COMSOL asignó), no `"selreg1_1"`.
- **`client.disconnect()`** en stand-alone lanza *"client is not connected to a server"* DESPUÉS
  de guardar. Envuélvelo en try/except; el `.mph` ya está en disco.
- El renglón rojo *"The client is not connected to a server"* al FINAL es ruido del cierre del
  JVM, **no** un fallo (si antes salió "guardado en …").
- Crea las features con su tipo COMSOL exacto: `SchrodingerEquation`, `EffectiveMass` (`meff1`),
  `ElectronPotentialEnergy` (props `Ve_src`, `Ve`), `Square`/`Circle`/`Ellipse`/`ParametricCurve`,
  `Eigenvalue`. (Identificadores tomados de un `.mph` real de COMSOL 5.6.)

---

## 5. Checklist de verificación del `.mph` generado

Un `.mph` es un ZIP; abre `dmodel.xml` y comprueba:

- [ ] `op="SchrodingerEquation"` presente (no `CoefficientFormPDE`).
- [ ] `ParametricCurve` con las expresiones x(s), y(s) en parámetros (R2, n…).
- [ ] El nodo `ElectronPotentialEnergy` por defecto (`ve1`) tiene `entityFlags` con **`DISABLED`**.
- [ ] Hay **un nodo de potencial por zona**, con `Ve_src='userdef'` y el `Ve` correcto
      (p. ej. canal `0[eV]`, barreras `Vb`), cada uno con su selección (`Ball`/`Union`).
- [ ] Las zonas son disjuntas y cubren todos los dominios (canal + barreras = todo).
- [ ] La tabla de `parameters` está (R1, R2, n, Vb…) → barridos posibles.
- [ ] Estudio `Eigenvalue` con `neigs`.

Comprobación rápida en Python:
```python
import zipfile, re
data = zipfile.ZipFile("session/model.mph").read("dmodel.xml").decode("utf-8","replace")
print("schr:", "SchrodingerEquation" in data)
for m in re.finditer(r'op="ElectronPotentialEnergy" tag="([^"]+)".*?<entityFlags[^>]*>([^<]*)<', data, re.DOTALL):
    print(m.group(1), m.group(2))   # ve1 debe decir DISABLED; los demás activos
```

**Test automático de regresión** (no necesita COMSOL): `python test_mph.py`. Verifica que el
reparto región/complemento sea disjunto y completo, detecta zonas solapadas, y de paso revisa
tu `session/design.json` actual avisando si alguna zona se solapa. Córrelo después de tocar
`core/exporter_mph.py` o `core/comsol_export.py`.

---

## 6. Cómo se genera (flujo del usuario, sin MATLAB)

```
python -m qpot export --format mph     # → session/model.mph (abre directo en COMSOL)
```
- En 2D usa `core.exporter_mph.export_mph_geometry` (geometría + schr, este documento).
- Si no hay MPh, cae con gracia a la **receta** (`comsol_recipe.md`), que reproduce estos mismos
  pasos a mano.
- La receta y el `.m` (`--format recipe` / `--format m`) siguen las **mismas** reglas.
