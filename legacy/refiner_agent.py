"""
Refiner agent: toma un Design + feedback del verifier y produce un Design
corregido que mantiene lo bueno y arregla lo malo.
"""

from __future__ import annotations
import os
import json
import re
import base64
from dataclasses import dataclass

import anthropic
from .prompts import refiner_system


_MODEL  = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
_CLIENT = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _CLIENT


@dataclass
class RefinerOutput:
    design: dict
    reasoning: str
    changes_summary: str
    raw_response: str


def refine(
    current_design: dict,
    verifier_feedback: dict,                # {score, matches, mismatches, suggestions, verdict}
    original_image: bytes | None = None,
    original_mime: str = "image/png",
    rendered_image: bytes | None = None,
    text_description: str | None = None,
) -> RefinerOutput:
    """Genera un Design refinado."""

    user_content = []

    if original_image is not None:
        user_content.append({"type": "text", "text": "IMAGEN ORIGINAL:"})
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": original_mime,
                       "data": base64.standard_b64encode(original_image).decode()},
        })

    if rendered_image is not None:
        user_content.append({"type": "text", "text": "RENDER ACTUAL (el que debes mejorar):"})
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png",
                       "data": base64.standard_b64encode(rendered_image).decode()},
        })

    feedback_text = (
        "FEEDBACK DEL VERIFICADOR:\n"
        f"  Score: {verifier_feedback.get('score', '?')}/10\n"
        f"  Veredicto: {verifier_feedback.get('verdict', '?')}\n\n"
        f"  Coincide (NO TOCAR):\n  - " +
        "\n  - ".join(verifier_feedback.get("matches", [])) + "\n\n"
        f"  NO coincide (CORREGIR):\n  - " +
        "\n  - ".join(verifier_feedback.get("mismatches", [])) + "\n\n"
        f"  Sugerencias:\n  - " +
        "\n  - ".join(verifier_feedback.get("suggestions", []))
    )

    user_content.append({"type": "text", "text": feedback_text})

    if text_description:
        user_content.append({
            "type": "text",
            "text": f"DESCRIPCIÓN ORIGINAL EN TEXTO:\n{text_description}",
        })

    user_content.append({
        "type": "text",
        "text": (
            "DESIGN ACTUAL:\n" + json.dumps(current_design, indent=2, ensure_ascii=False) +
            "\n\nProduce el Design refinado siguiendo el formato establecido."
        ),
    })

    dim = current_design.get("dim", 2)
    response = _client().messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=refiner_system(dim=dim),
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text
    return _parse_refiner(raw)


def _parse_refiner(raw: str) -> RefinerOutput:
    reasoning = _extract(raw, "reasoning")
    design_str = _extract(raw, "design")
    summary = _extract(raw, "changes_summary")

    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", design_str.strip())
    try:
        design = json.loads(cleaned)
    except Exception as e:
        raise ValueError(f"Refiner devolvió JSON inválido:\n{design_str}\n{e}")

    return RefinerOutput(
        design=design,
        reasoning=reasoning.strip(),
        changes_summary=summary.strip(),
        raw_response=raw,
    )


def _extract(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    if tag == "design":
        jm = re.search(r"\{.*\}", text, re.DOTALL)
        if jm: return jm.group()
    return ""
