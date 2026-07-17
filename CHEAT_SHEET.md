# Referencia rápida 1.0

```bash
qpot project new nombre --dim 2 --material GaAs
qpot project list
qpot project open nombre
qpot from-preset quantum_ring --dim 2
qpot param R1 12
qpot state
qpot render --html
qpot target --description "objetivo" --features '{"ring_like":true}'
qpot verify
qpot assess --score 8 --render-inspected --matches '["anillo"]'
qpot sweep R1 --range=10:20:6
qpot export --format recipe
qpot export --format mph
qpot project export nombre
qpot ui
```

Unidades: nm y eV. Workspace: `workspace/` o `QPOT_WORKSPACE_DIR`.
