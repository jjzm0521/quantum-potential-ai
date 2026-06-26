# Referencia de primitivas y esquema del Design (qpot)

> Archivo generado desde `ai/primitives_spec.py` (fuente unica). Regenera con el bloque del README.

Un **Design** es un JSON con `dim`, `material`, `domain`, un bloque opcional `parameters`
(p. ej. `{"R1":12,"R2":28,"n":7,"Vb":0.228}`) y una lista de `pieces` que se **suman** para
formar V(x) (1D) o V(x,y) (2D). Coordenadas en **nm**, energias en **eV**. Las args/value de
las piezas pueden ser un numero o el NOMBRE de un parametro (string), p. ej. `"R":"R2"`.

## Esquema JSON

```
DESIGN JSON SCHEMA:
{
  "dim": 2,                          // 1 o 2
  "material": "GaAs|InAs|InGaAs|Si|GaN|libre",
  "domain": {"L": <float nm>, "N": <int>},     // dominio cuadrado [-L/2, L/2]², grilla N×N
  "pieces": [
    {
      "label": "<descripción humana>",         // opcional
      "enabled": true,                          // opcional, default true
      "op": "<nombre_primitiva>",
      "args": {<argumentos>}
    },
    // ...para 'mask' o 'where':
    {
      "op": "mask",
      "region": { "op": "<región>", "args": {...} },
      "value": <float eV>
    },
    {
      "op": "where",
      "region": { "op": "<región>", "args": {...} },
      "inner": { "op": "...", "args": {...} },
      "outer": { "op": "constant", "args": {"value": 0} }
    }
  ]
}

REGLAS:
- Coordenadas en nm. Potencial en eV.
- Las pieces se SUMAN entre sí (orden no importa salvo por composiciones).
- Si no estás seguro de un parámetro, usa valores típicos del material.
- Usa raw_expr SOLO si ninguna primitiva sirve (último recurso).
```

## Primitivas disponibles

```
═══ PRIMITIVAS 1D (para problemas en una dimensión, V(x)) ═══

REGIONES 1D (intervalos — usar dentro de 'mask' o 'where'):

  • interval(center=0.0[nm], length=20.0[nm])
      Intervalo [center-L/2, center+L/2].
      - center: centro del intervalo
      - length: longitud total

  • half_line(side=positive, position=0.0[nm])
      Semi-recta a un lado de 'position'.
      - side: 'positive' (x≥pos) o 'negative' (x≤pos)

  • strip(x_min=-10.0[nm], x_max=10.0[nm])
      Intervalo asimétrico [x_min, x_max].


PERFILES DE POTENCIAL 1D (V en eV — se SUMAN entre sí):

  • constant(value=0.0[eV])
      V = value constante.

  • gaussian(center=0.0[nm], amplitude=-0.3[eV], sigma=10.0[nm])
      Gaussiana 1D: pozo o barrera suave.
      - amplitude: negativo→pozo, positivo→barrera

  • harmonic(center=0.0[nm], omega_eV=0.0005[eV/nm²])
      Oscilador armónico 1D — soluble analíticamente.
      - omega_eV: ½·ω·(x-x₀)². Típico: 1e-4 a 1e-3

  • coulomb(center=0.0[nm], charge=1.0[e], eps_r=12.9, regularization=1.0[nm])
      Impureza Coulomb 1D regularizada (soft).
      - charge: +1 donante, -1 aceptor
      - regularization: corte para evitar singularidad

  • linear(slope=0.001[eV/nm], offset=0.0[eV])
      V = slope·x + offset. Campo eléctrico uniforme.
      - slope: campo eléctrico Stark

  • polynomial(coeffs=[{'i': 2, 'c': 0.0005}][eV/nmⁱ], center=0.0[nm])
      Polinomio univariado: c₁(x-x₀) + c₂(x-x₀)² + ...
      - coeffs: lista de {i,c} → c·(x-x₀)ⁱ

  • exp_decay(center=0.0[nm], amplitude=-0.3[eV], length=10.0[nm])
      Decaimiento exponencial: V = amp·exp(-|x-x₀|/length).
      - length: longitud de decaimiento

  • poschl_teller(center=0.0[nm], depth=0.3[eV], alpha=0.1[nm⁻¹])
      Pöschl-Teller: -V₀/cosh²(α(x-x₀)). Soluble analíticamente.
      - alpha: inverso del ancho del solitón

  • morse(De=0.3[eV], a=0.1[nm⁻¹], x0=0.0[nm])
      Potencial de Morse — molécula diatómica anharmónica.
      - De: profundidad disociación
      - a: inverso longitud
      - x0: equilibrio

  • step(position=0.0[nm], height=0.2[eV])
      Escalón de Heaviside.

  • barrier(center=0.0[nm], height=0.3[eV], width=10.0[nm])
      Barrera rectangular (tunneling).

  • infinite_wall(position=0.0[nm], side=left, V_inf=1000.0[eV])
      Pared infinita (V muy alto en un lado).
      - side: 'left' (x≤pos) o 'right' (x≥pos)

  • triangular(slope=0.005[eV/nm], x_wall=-50.0[nm], V_inf=1000.0)
      Triangular (Stark con muro): V=slope·(x-x_wall) + pared a la izq.
      - slope: campo Stark
      - x_wall: posición del muro infinito

  • raw_expr(expr=0.5*0.0005*x**2)
      Expresión matemática arbitraria. Último recurso para formas exóticas.
      - expr: expresión numpy. Variable: x. Funciones: sin,cos,exp,sqrt,abs,...


═══ PRIMITIVAS 2D (para problemas planares, V(x,y)) ═══

REGIONES 2D (devuelven máscara booleana — dentro de 'mask' o 'where'):

  • disk(center=[0.0, 0.0][nm], radius=10.0[nm])
      Disco circular.
      - center: centro [x,y]
      - radius: radio

  • annulus(center=[0.0, 0.0][nm], r_inner=10.0[nm], r_outer=20.0[nm])
      Anillo entre dos radios.
      - center: centro
      - r_inner: radio interior
      - r_outer: radio exterior

  • rectangle(center=[0.0, 0.0][nm], Lx=20.0[nm], Ly=20.0[nm], angle_deg=0.0[°])
      Rectángulo centrado, opcionalmente rotado.
      - center: centro
      - Lx: ancho x
      - Ly: alto y
      - angle_deg: rotación

  • ellipse(center=[0.0, 0.0][nm], a=15.0[nm], b=10.0[nm], angle_deg=0.0[°])
      Elipse estándar (x/a)²+(y/b)²<=1.
      - a: semieje x
      - b: semieje y

  • super_ellipse(center=[0.0, 0.0][nm], a=15.0[nm], b=15.0[nm], n=4.0, angle_deg=0.0[°])
      Super-elipse |x/a|^n+|y/b|^n<=1. Muy útil para puntos cuánticos AFM.
      - n: exponente: 2=elipse, 4=cuadrado redondeado, >>2=rectángulo, <2=estrella

  • rose(center=[0.0, 0.0][nm], k=4, R=20.0[nm], angle_deg=0.0[°])
      Roseta r<=R·|cos(kθ)|. Para puntos cuánticos con pétalos.
      - k: número de pétalos (par→2k, impar→k)
      - R: radio máximo

  • hypocycloid(center=[0.0, 0.0][nm], R=20.0[nm], n=5, angle_deg=0.0[°])
      Interior de una hipocicloide (estrella de n puntas hacia adentro). Frontera interna tipo COMSOL definida por R y n.
      - R: radio característico
      - n: nº de ciclos/cúspides (entero ≥3)
      - angle_deg: rotación

  • epicycloid(center=[0.0, 0.0][nm], R=20.0[nm], n=5, angle_deg=0.0[°])
      Interior de una epicicloide (flor de n lóbulos hacia afuera). Frontera externa tipo COMSOL definida por R y n.
      - R: radio característico
      - n: nº de ciclos/lóbulos (entero ≥3)
      - angle_deg: rotación

  • polygon(vertices=[[-10.0, -10.0], [10.0, -10.0], [10.0, 10.0], [-10.0, 10.0]][nm])
      Polígono arbitrario.
      - vertices: lista de [x,y]

  • half_plane(axis=x, position=0.0[nm], side=positive)
      Semi-plano respecto a un eje.
      - axis: 'x' o 'y'
      - side: 'positive' o 'negative'


PERFILES DE POTENCIAL 2D (V en eV — se SUMAN entre sí):

  • constant(value=0.0[eV])
      V = value en todas partes. Útil con mask/where.
      - value: valor constante

  • gaussian(center=[0.0, 0.0][nm], amplitude=-0.3[eV], sigma=20.0[nm])
      Gaussiana 2D. Bloque básico para pozos/barreras suaves.
      - amplitude: negativo→pozo, positivo→barrera
      - sigma: ancho

  • mexican_hat(center=[0.0, 0.0][nm], r0=30.0[nm], depth=0.3[eV])
      Anillo cuántico (sombrero mexicano).
      - r0: radio del mínimo
      - depth: profundidad del valle

  • harmonic_2d(center=[0.0, 0.0][nm], omega_eV=0.0002[eV/nm²])
      Parabólico isótropo 2D.
      - omega_eV: curvatura ½·ω·r²

  • harmonic_anisotropic(center=[0.0, 0.0][nm], omega_x=0.0002[eV/nm²], omega_y=0.0002[eV/nm²])
      Parabólico anisótropo (distintas curvaturas en x e y).

  • coulomb(center=[0.0, 0.0][nm], charge=1.0[e], eps_r=12.9, regularization=1.0[nm])
      Impureza Coulomb soft. Ry*≈5.5meV en GaAs, a*≈10nm.
      - charge: +1 donante, -1 aceptor
      - eps_r: constante dieléctrica
      - regularization: radio de corte para evitar singularidad

  • linear(slope=0.001[eV/nm], axis=x, offset=0.0[eV])
      Término lineal: campo eléctrico uniforme V=F·x.
      - slope: pendiente (campo eléctrico)
      - axis: 'x' o 'y'

  • polynomial(center=[0.0, 0.0][nm], coeffs=[{'i': 2, 'j': 0, 'c': 0.001}][eV/nm^(i+j)])
      Polinomio bivariado arbitrario.
      - coeffs: lista de {i,j,c} → c·xⁱ·yʲ

  • exp_decay(center=[0.0, 0.0][nm], amplitude=-0.3[eV], length=20.0[nm])
      Decaimiento exponencial radial.
      - length: longitud de decaimiento

  • poschl_teller(center=[0.0, 0.0][nm], depth=0.3[eV], alpha=0.05[nm⁻¹])
      Pöschl-Teller radial: -V₀/cosh²(αr).
      - alpha: inverso del ancho

  • raw_expr(expr=0.5*0.0002*(x**2+y**2))
      Expresión matemática arbitraria. Último recurso para formas exóticas.
      - expr: expresión numpy. Variables: x,y,r,theta. Funciones: sin,cos,exp,sqrt,...


OPERACIONES COMPUESTAS (funcionan en 1D y 2D):

  • mask(region, value): aplica 'value' (eV) dentro de la región, 0 fuera.
  • where(region, inner, outer): 'inner' dentro, 'outer' fuera.
  • clamp(inner, V_min, V_max): recorta al rango.
  • scale(inner, factor): multiplica por escalar.
  • union/intersection/complement: combina regiones.
```
