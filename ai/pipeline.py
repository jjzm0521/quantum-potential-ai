"""
Pipeline: orquesta el loop completo
  designer → validar → verifier → refiner (loop) → resultado final

Devuelve un PipelineResult con todo el rastro (analysis, scores, renders,
iteraciones) para mostrar al usuario en la UI.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .designer_agent import design_from_text, design_from_image, DesignerOutput
from .verifier_agent import verify, VerifierOutput
from .refiner_agent import refine, RefinerOutput
from .validators import validate_design
from .event_log import EventLog


# Umbrales
SCORE_OK_THRESHOLD = 7         # ≥ 7 → no refinar más
MAX_REFINE_ITERATIONS = 3


@dataclass
class IterationTrace:
    iteration: int                          # 0 = designer original, 1+ = refinador
    design: dict
    validator_issues: list[str]             # del validador numérico
    verifier: VerifierOutput | None         # None si no se llamó al verifier
    reasoning: str                          # analysis (iter 0) o reasoning del refiner
    changes_summary: str = ""               # solo en iters > 0


@dataclass
class PipelineResult:
    final_design: dict
    final_score: int
    final_confidence: str                   # alta/media/baja
    iterations: list[IterationTrace]
    designer_output: DesignerOutput | None  # primera respuesta del designer
    converged: bool                          # True si score >= threshold
    error: str | None = None
    run_id: str | None = None                # id del event log (carpeta runs/{run_id})
    run_dir: str | None = None


def run_pipeline_from_text(
    description: str,
    enable_verifier: bool = True,
    enable_refiner: bool = True,
    force_dim: int = 0,
    log_events: bool = True,
) -> PipelineResult:
    """Pipeline completo desde descripción textual. force_dim=1, 2 o 0 (auto)."""
    return _run(
        designer_call=lambda: design_from_text(description, force_dim=force_dim),
        original_image=None,
        original_mime=None,
        text_description=description,
        enable_verifier=enable_verifier,
        enable_refiner=enable_refiner,
        log_events=log_events,
        source="text",
    )


def run_pipeline_from_image(
    image_bytes: bytes,
    mime_type: str = "image/png",
    extra_context: str = "",
    enable_verifier: bool = True,
    enable_refiner: bool = True,
    force_dim: int = 0,
    log_events: bool = True,
) -> PipelineResult:
    """Pipeline completo desde imagen. force_dim=1, 2 o 0 (auto)."""
    return _run(
        designer_call=lambda: design_from_image(image_bytes, mime_type,
                                                  extra_context, force_dim=force_dim),
        original_image=image_bytes,
        original_mime=mime_type,
        text_description=extra_context or None,
        enable_verifier=enable_verifier,
        enable_refiner=enable_refiner,
        log_events=log_events,
        source="image",
    )


def _run(
    designer_call,
    original_image: bytes | None,
    original_mime: str | None,
    text_description: str | None,
    enable_verifier: bool,
    enable_refiner: bool,
    log_events: bool = True,
    source: str = "text",
) -> PipelineResult:

    iterations: list[IterationTrace] = []

    log = EventLog() if log_events else None
    run_id = log.run_id if log else None
    run_dir = str(log.dir) if log else None

    def _emit(t: str, payload: dict | None = None) -> None:
        if log:
            log.emit(t, payload or {})

    _emit("pipeline_start", {
        "source": source,
        "has_image": original_image is not None,
        "text_description": text_description,
        "enable_verifier": enable_verifier,
        "enable_refiner": enable_refiner,
        "score_threshold": SCORE_OK_THRESHOLD,
        "max_refine_iters": MAX_REFINE_ITERATIONS,
    })
    if log and original_image is not None:
        ext = (original_mime or "image/png").split("/")[-1].split("+")[0]
        log.save_blob(f"original.{ext}", original_image)

    # --- Paso 1: Designer ---
    try:
        designer_out = designer_call()
    except Exception as e:
        _emit("designer_failed", {"error": str(e)})
        return PipelineResult(
            final_design={"dim": 2, "pieces": []},
            final_score=0,
            final_confidence="baja",
            iterations=[],
            designer_output=None,
            converged=False,
            error=f"Designer falló: {e}",
            run_id=run_id,
            run_dir=run_dir,
        )

    current_design = designer_out.design
    validator_issues = validate_design(current_design)

    iter0 = IterationTrace(
        iteration=0,
        design=current_design,
        validator_issues=validator_issues,
        verifier=None,
        reasoning=designer_out.analysis,
    )
    iterations.append(iter0)
    _emit("designer_done", {
        "design": current_design,
        "analysis": designer_out.analysis,
        "confidence": designer_out.confidence,
    })
    _emit("validator_done", {"iteration": 0, "issues": validator_issues})

    # --- Paso 2-N: Verificación + Refinamiento ---
    if not enable_verifier:
        _emit("skipped_verifier", {})
        _emit("pipeline_end", {"converged": True, "final_score": -1})
        return PipelineResult(
            final_design=current_design,
            final_score=-1,
            final_confidence=designer_out.confidence,
            iterations=iterations,
            designer_output=designer_out,
            converged=True,
            run_id=run_id,
            run_dir=run_dir,
        )

    last_score = 0
    last_render = None
    for it in range(MAX_REFINE_ITERATIONS + 1):
        try:
            v = verify(
                design=current_design,
                original_image=original_image,
                original_mime=original_mime or "image/png",
                text_description=text_description,
            )
        except Exception as e:
            # Verifier falló — devolver lo que tengamos
            iterations[-1].verifier = None
            _emit("verifier_failed", {"iteration": it, "error": str(e)})
            return PipelineResult(
                final_design=current_design,
                final_score=last_score,
                final_confidence=designer_out.confidence,
                iterations=iterations,
                designer_output=designer_out,
                converged=False,
                error=f"Verifier falló en iter {it}: {e}",
                run_id=run_id,
                run_dir=run_dir,
            )

        # Anotar el verifier en la iteración actual
        iterations[-1].verifier = v
        last_score = v.score
        last_render = v.render_png

        if log and v.render_png:
            log.save_blob(f"render_iter{it}.png", v.render_png)
        _emit("verifier_done", {
            "iteration": it,
            "score": v.score,
            "verdict": v.verdict,
            "matches": v.matches,
            "mismatches": v.mismatches,
            "suggestions": v.suggestions,
        })

        # ¿Convergió?
        if v.score >= SCORE_OK_THRESHOLD or v.verdict == "ok":
            _emit("pipeline_end", {"converged": True, "final_score": v.score, "iterations": it + 1})
            return PipelineResult(
                final_design=current_design,
                final_score=v.score,
                final_confidence=designer_out.confidence,
                iterations=iterations,
                designer_output=designer_out,
                converged=True,
                run_id=run_id,
                run_dir=run_dir,
            )

        # Si no podemos refinar más, salir
        if not enable_refiner or it >= MAX_REFINE_ITERATIONS:
            break

        # --- Refinar ---
        try:
            r = refine(
                current_design=current_design,
                verifier_feedback={
                    "score": v.score,
                    "matches": v.matches,
                    "mismatches": v.mismatches,
                    "suggestions": v.suggestions,
                    "verdict": v.verdict,
                },
                original_image=original_image,
                original_mime=original_mime or "image/png",
                rendered_image=v.render_png,
                text_description=text_description,
            )
        except Exception as e:
            _emit("refiner_failed", {"iteration": it + 1, "error": str(e)})
            return PipelineResult(
                final_design=current_design,
                final_score=last_score,
                final_confidence=designer_out.confidence,
                iterations=iterations,
                designer_output=designer_out,
                converged=False,
                error=f"Refiner falló en iter {it+1}: {e}",
                run_id=run_id,
                run_dir=run_dir,
            )

        current_design = r.design
        validator_issues = validate_design(current_design)
        iterations.append(IterationTrace(
            iteration=it + 1,
            design=current_design,
            validator_issues=validator_issues,
            verifier=None,
            reasoning=r.reasoning,
            changes_summary=r.changes_summary,
        ))
        _emit("refiner_done", {
            "iteration": it + 1,
            "design": current_design,
            "reasoning": r.reasoning,
            "changes_summary": r.changes_summary,
        })
        _emit("validator_done", {"iteration": it + 1, "issues": validator_issues})

    # Salimos del loop sin converger
    _emit("pipeline_end", {"converged": False, "final_score": last_score})
    return PipelineResult(
        final_design=current_design,
        final_score=last_score,
        final_confidence=designer_out.confidence,
        iterations=iterations,
        designer_output=designer_out,
        converged=False,
        run_id=run_id,
        run_dir=run_dir,
    )
