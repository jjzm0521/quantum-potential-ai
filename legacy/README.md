# legacy/ — código archivado (visor Streamlit + pipeline de IA con API)

### Visor Streamlit (`app.py`)
El visor humano interactivo (sliders en vivo). Se archivó porque el flujo nuevo usa el CLI:
para ver el potencial usa `python -m qpot render` (PNG limpio) o `python -m qpot render --html`
(superficie 3D interactiva en el navegador, sin servidor). Si quieres correrlo igual:
`pip install streamlit plotly && python -m streamlit run legacy/app.py`.

### Pipeline de IA (con API de Anthropic)
El pipeline multi-agente original que llamaba a la **API de Anthropic** para componer, verificar
y refinar potenciales:

- `vision_agent.py` — análisis de texto/imagen → potencial sugerido.
- `designer_agent.py` — propone el Design JSON inicial.
- `verifier_agent.py` — compara render vs. imagen original y califica.
- `refiner_agent.py` — corrige el Design según el feedback.
- `pipeline.py` — orquesta el loop Designer → Verifier → Refiner.
- `prompts.py` — system prompts y few-shots de esos agentes.

## ¿Por qué está aquí y no en el flujo principal?

El proyecto pasó a un modelo **estilo Text2CAD**: el "cerebro" es el LLM que el estudiante
ya tiene abierto (Claude Code / ChatGPT / Codex / Antigravity), que maneja el repo con el
CLN `qpot` **sin pagar API**. El conocimiento físico y la estrategia de estos agentes se
trasladó a [`../AGENTS.md`](../AGENTS.md).

## ¿Cómo correrlo si lo necesitas?

```bash
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...
python -c "from legacy.pipeline import run_pipeline_from_text; print(run_pipeline_from_text('pozo finito GaAs 30 nm 250 meV'))"
```

> Nota: se mantiene por valor de referencia/auditoría. El flujo recomendado es `python -m qpot`.
