"""
Verifier agent: compara visualmente la imagen original con un render
del Design para detectar mismatches.

Si no hay imagen original (input fue solo texto), el verifier hace
auto-crítica usando solo el render + la descripción textual.
"""

from __future__ import annotations
import os
import io
import base64
import json
import re
from dataclasses import dataclass

import anthropic
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .prompts import VERIFIER_SYSTEM
from core.composer import evaluate_design, evaluate_design_1d


_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
_CLIENT = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _CLIENT


@dataclass
class VerifierOutput:
    score: int                  # 0-10
    matches: list[str]
    mismatches: list[str]
    suggestions: list[str]
    verdict: str                # ok | necesita_refinamiento | fundamentalmente_incorrecto
    render_png: bytes           # PNG del render para mostrar al usuario
    raw_response: str


def verify(
    design: dict,
    original_image: bytes | None = None,
    original_mime: str = "image/png",
    text_description: str | None = None,
) -> VerifierOutput:
    """
    Verifica un Design.
      - Si hay imagen original: comparación visual de las dos imágenes
      - Si no: auto-crítica usando descripción de texto + render
    """
    render = _render_design_png(design)

    user_content = []

    if original_image is not None:
        b64_orig = base64.standard_b64encode(original_image).decode()
        user_content.append({"type": "text", "text": "IMAGEN ORIGINAL:"})
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": original_mime, "data": b64_orig},
        })

    user_content.append({"type": "text", "text": "RENDER DEL POTENCIAL GENERADO:"})
    user_content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png",
                   "data": base64.standard_b64encode(render).decode()},
    })

    if text_description:
        user_content.append({
            "type": "text",
            "text": f"DESCRIPCIÓN ORIGINAL EN TEXTO:\n{text_description}",
        })

    user_content.append({
        "type": "text",
        "text": ("Compara y emite el JSON de evaluación según el formato indicado."),
    })

    response = _client().messages.create(
        model=_MODEL,
        max_tokens=1500,
        system=VERIFIER_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text
    return _parse_verifier(raw, render)


# ---------------------------------------------------------------------------
# Render del Design a PNG
# ---------------------------------------------------------------------------

def _render_design_png(design: dict, size_px: int = 500) -> bytes:
    """Renderiza el Design como PNG (1D = plot V(x), 2D = heatmap)."""
    dim = design.get("dim", 2)
    L = design.get("domain", {}).get("L", 120.0 if dim == 1 else 200.0)
    N = design.get("domain", {}).get("N", 1024 if dim == 1 else 96)

    if dim == 1:
        return _render_1d(design, L, N, size_px)
    else:
        return _render_2d(design, L, N, size_px)


def _render_2d(design: dict, L: float, N: int, size_px: int) -> bytes:
    x = np.linspace(-L/2, L/2, N)
    y = np.linspace(-L/2, L/2, N)
    X, Y = np.meshgrid(x, y)
    V = evaluate_design(design, X, Y)
    V_plot = np.clip(V, np.percentile(V, 1), np.percentile(V, 99))

    fig, ax = plt.subplots(figsize=(5, 5), dpi=size_px / 5)
    im = ax.imshow(V_plot, extent=[-L/2, L/2, -L/2, L/2],
                    origin="lower", cmap="RdBu_r", aspect="equal")
    plt.colorbar(im, ax=ax, label="V (eV)")
    ax.set_xlabel("x (nm)"); ax.set_ylabel("y (nm)")
    ax.set_title("Render del Design (2D)")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=size_px / 5)
    plt.close(fig)
    return buf.getvalue()


def _render_1d(design: dict, L: float, N: int, size_px: int) -> bytes:
    x = np.linspace(-L/2, L/2, N)
    V = evaluate_design_1d(design, x)
    # Clamp para visualización (evitar que las paredes infinitas arruinen la escala)
    V_finite = V[np.abs(V) < 100]
    if len(V_finite) > 0:
        v_max = np.percentile(V_finite, 99) + 0.05
        v_min = np.min(V_finite) - 0.05
    else:
        v_max, v_min = 1.0, -1.0
    V_show = np.clip(V * 1000, v_min*1000, v_max*1000)  # meV

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=size_px / 5)
    ax.plot(x, V_show, color="#1f77b4", linewidth=2)
    ax.fill_between(x, V_show, V_show.min()-50, alpha=0.15, color="#1f77b4")
    ax.set_xlabel("x (nm)", fontsize=11)
    ax.set_ylabel("V (meV)", fontsize=11)
    ax.set_title("Render del Design (1D) — V(x)", fontsize=12)
    ax.grid(alpha=0.3)
    # Línea de referencia en V=0
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=size_px / 5)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_verifier(raw: str, render_png: bytes) -> VerifierOutput:
    # Extraer JSON
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return VerifierOutput(
            score=0, matches=[], mismatches=["Verifier no devolvió JSON"],
            suggestions=[], verdict="fundamentalmente_incorrecto",
            render_png=render_png, raw_response=raw,
        )
    try:
        data = json.loads(m.group())
    except Exception as e:
        return VerifierOutput(
            score=0, matches=[], mismatches=[f"JSON inválido: {e}"],
            suggestions=[], verdict="fundamentalmente_incorrecto",
            render_png=render_png, raw_response=raw,
        )

    return VerifierOutput(
        score=int(data.get("score", 0)),
        matches=list(data.get("matches", [])),
        mismatches=list(data.get("mismatches", [])),
        suggestions=list(data.get("suggestions", [])),
        verdict=str(data.get("verdict", "necesita_refinamiento")),
        render_png=render_png,
        raw_response=raw,
    )
