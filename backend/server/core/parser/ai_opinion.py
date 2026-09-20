"""
NeuroPlan-3D — AI "Gut Check" Opinion (demo/credibility feature)

This module exists to make the project's core claim ("AI proposes, physics
decides") visible and checkable, not just a tagline. It asks the AI for its
own unverified opinion on whether a structure sounds safe — using only the
natural-language description, with no access to the solver, no stiffness
matrix, no calculation of any kind — and returns that alongside (but never
influencing) the real FEA verdict.

This opinion is explicitly NOT engineering analysis. It exists specifically
to be compared against the real, deterministic solver result so the gap
between "sounds plausible" and "is actually verified" is visible to a user,
not asserted in a slide.
"""
import json
import re

from ...models.structure import EngineeringSpec
from ...config import GEMINI_API_KEY, GEMINI_MODEL


OPINION_PROMPT = """You are giving a quick, informal gut-check opinion on a proposed \
structure — NOT a real engineering analysis. You have no access to a structural \
solver and must NOT attempt any calculation. Based purely on how the description \
sounds, give your intuitive impression.

Structure description: span {span}m, height {height}m, {geometry_note}{num_panels}-panel \
{structure_type} truss, {load_kn} kN {load_description}{lateral_note}, material \
{material_key}, safety factor {safety_factor}.

Respond with ONLY valid JSON:
{{
  "verdict": "likely_safe" or "likely_unsafe" or "uncertain",
  "confidence": "low" or "medium" or "high",
  "reasoning": "<one sentence, no calculation, just intuition>"
}}
"""


def get_ai_naive_opinion(spec: EngineeringSpec) -> dict:
    """
    Ask the AI for an unverified, no-calculation opinion on whether the
    structure sounds safe. Falls back to a deliberately crude heuristic
    (explicitly labeled as such) when no API key is configured, so the
    comparison feature works in both modes.
    """
    if not GEMINI_API_KEY:
        return _naive_heuristic_opinion(spec)

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        lateral_parts = []
        if spec.lateral_load_x:
            lateral_parts.append(f"{spec.lateral_load_x / 1000:g} kN longitudinal")
        if spec.lateral_load_z:
            lateral_parts.append(f"{spec.lateral_load_z / 1000:g} kN transverse")

        prompt = OPINION_PROMPT.format(
            span=spec.span,
            height=spec.height,
            geometry_note=(f"{spec.width}m wide 3D space truss, " if spec.structure_type.is_spatial else ""),
            num_panels=spec.num_panels,
            structure_type=spec.structure_type.value,
            load_kn=spec.primary_load / 1000,
            load_description=spec.load_description,
            lateral_note=(" plus " + " and ".join(lateral_parts) if lateral_parts else ""),
            material_key=spec.material_key,
            safety_factor=spec.safety_factor,
        )
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)

        data = json.loads(text)
        return {
            "verdict": data.get("verdict", "uncertain"),
            "confidence": data.get("confidence", "low"),
            "reasoning": data.get("reasoning", ""),
            "source": "gemini",
        }
    except Exception as e:
        result = _naive_heuristic_opinion(spec)
        result["reasoning"] = f"(AI call failed: {e}) " + result["reasoning"]
        return result


def _naive_heuristic_opinion(spec: EngineeringSpec) -> dict:
    """
    A deliberately crude, non-physics heuristic used only when no AI is
    configured. It exists purely to keep the comparison feature functional
    without an API key — it is intentionally simplistic (a raw span/load
    ratio, no material, section, or actual stress check) so it should NOT
    be trusted, which is exactly the point being demonstrated.
    """
    # Purely cosmetic "plausibility" check — no engineering meaning.
    load_to_span_kn_per_m = (spec.primary_load / 1000) / max(spec.span, 1e-6)
    if load_to_span_kn_per_m < 3:
        verdict = "likely_safe"
        reasoning = "Load relative to span looks modest at a glance — no calculation performed."
    elif load_to_span_kn_per_m < 8:
        verdict = "uncertain"
        reasoning = "Load relative to span looks moderate — no calculation performed."
    else:
        verdict = "likely_unsafe"
        reasoning = "Load relative to span looks high at a glance — no calculation performed."

    return {
        "verdict": verdict,
        "confidence": "low",
        "reasoning": reasoning,
        "source": "heuristic_fallback",
    }
