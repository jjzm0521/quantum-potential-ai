# CLAUDE.md

Este proyecto convierte descripciones (texto o imagen) de **potenciales cuánticos** en
simulaciones de Schrödinger 1D/2D y exportación a COMSOL — **sin usar ninguna API de pago**.

**Tú eres el cerebro.** No hay pipeline de IA embebido: tú construyes, ves, verificas y
refinas el potencial usando el CLI `qpot`.

👉 **Lee [AGENTS.md](AGENTS.md)** antes de empezar. Contiene el flujo de trabajo
(Designer → Verify → Refiner), la referencia de comandos y las escalas físicas.
La referencia de primitivas y el esquema del Design están en [PRIMITIVES.md](PRIMITIVES.md).

Arranque típico:
```
qpot project new demo --dim 1 --material GaAs
qpot from-preset finite_well --dim 1 --params "{\"depth\":0.25,\"L\":30}"
qpot target --description "Pozo finito de 30 nm y 250 meV"
qpot verify   # renderiza el proyecto activo — ÁBRELO y míralo
```

El Design vive en el proyecto activo de `workspace/` (fuente de verdad). Para verlo:
`qpot render --html --open` (superficie 3D interactiva, sin servidor).
En Claude Code puedes lanzar el flujo completo con el comando `/potential`.
