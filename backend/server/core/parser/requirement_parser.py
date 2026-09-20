"""
NeuroPlan-3D — Natural Language Requirement Parser

Uses the Gemini API (structured output) to extract engineering
parameters from natural language descriptions.

Includes a fallback manual parser for when the API is unavailable.

The AI extracts parameters. It does NOT validate physics.
"""
import json
import re
import os
from ...models.structure import (
    DimensionalityIntent, EngineeringSpec, StructureType,
)
from ...config import GEMINI_API_KEY, GEMINI_MODEL
from .dimensionality import DimensionalityEvidence, detect_dimensionality


EXTRACTION_PROMPT = """You are a structural engineering specification extractor.

Given a natural language description of a structural engineering requirement,
extract the following parameters. Return ONLY valid JSON with these fields:

{
  "structure_type": "pratt" or "warren" or "howe" or "space_truss" (default: "pratt"),
  "span": <number in meters>,
  "height": <number in meters — structural depth, typically span/6 to span/4>,
  "width": <number in meters — transverse width; REQUIRED and > 0 for space_truss, 0 for planar types>,
  "num_panels": <integer, typically 6-12>,
  "primary_load": <number in Newtons — VERTICAL load magnitude>,
  "lateral_load_x": <number in Newtons — longitudinal load, e.g. braking. 0 if not mentioned>,
  "lateral_load_z": <number in Newtons — transverse load, e.g. wind. 0 if not mentioned>,
  "load_description": "center point load" or "distributed load",
  "material_key": "A36" or "A992" or "AL6061" (default: "A36"),
  "safety_factor": <number, default 1.67>,
  "max_displacement_ratio": <number, default 300>,
  "description": "<brief engineering description>",
  "specified_fields": [<list of the field names the user EXPLICITLY stated>]
}

Rules:
- Convert all units to SI (meters, Newtons, Pascals)
- If kN is mentioned, multiply by 1000 to get N
- If height is not specified, use span/6
- If num_panels is not specified, use 6 for spans <= 15m, 8 for <= 30m, 10 for > 30m
- If material is not specified, use A36
- Structure type: ANY three-dimensional intent -> "space_truss". That includes
  "3d", "3-d", "three dimensional", "space truss", "space frame", "spatial",
  "spatial truss", "box truss". A bare "3d" anywhere in the requirement is
  enough — never return a planar type for a requirement that says 3D.
  Otherwise: "warren" -> "warren"; "howe" -> "howe"; else "pratt"
- If space_truss is chosen and no width is given, use span/5
- If load position mentions "center" or "middle", use "center point load"
- If load mentions "distributed" or "uniform", use "distributed load"
- Mentions of "wind" or "transverse"/"lateral" load -> lateral_load_z
- Default safety_factor is 1.67 (ASD)
- Default displacement ratio is 300 (L/300)
- "specified_fields" must list ONLY fields the user actually stated. Do not
  include fields you inferred or defaulted. This is used to tell the user
  exactly which values were assumed on their behalf.

Return ONLY the JSON object, no explanation.
"""

# Human-readable descriptions for values the system fills in when the user
# did not state them. Phase 14: defaults are disclosed, never hidden.
_DEFAULT_MESSAGES = {
    "structure_type": "structure type",
    "span": "span",
    "height": "structural depth (height)",
    "width": "transverse width",
    "num_panels": "panel count",
    "primary_load": "vertical load",
    "material_key": "material",
    "section_key": "cross-section",
    "safety_factor": "safety factor",
    "max_displacement_ratio": "displacement limit",
    "load_description": "load distribution",
}


def _named_planar_type(text: str) -> StructureType:
    """The planar type the text names, defaulting to Pratt when none is named."""
    lowered = text.lower()
    if "warren" in lowered:
        return StructureType.WARREN
    if "howe" in lowered:
        return StructureType.HOWE
    return StructureType.PRATT


def _resolve_structure_type(
    spec: EngineeringSpec,
    evidence: DimensionalityEvidence,
    specified: set[str],
    *,
    proposed: StructureType | None = None,
) -> None:
    """
    Decide `spec.structure_type` from the dimensional evidence, and record
    how that decision was reached.

    This is the authoritative reading of what the user wrote. `proposed` is
    the AI's suggestion, which is honoured only where it does not contradict
    an explicit dimensional statement — an AI guess must never downgrade an
    explicit 3D request to a planar model.

    Any spatial term selects the spatial system, including when planar terms
    are also present ("2D space truss", "3D Pratt truss"): a space truss has
    no planar representation, so honouring the 3D term is the only reading
    that does not silently discard part of the requirement. The conflict is
    disclosed rather than resolved quietly.
    """
    spec.dimensionality_intent = evidence.intent
    text = spec.raw_input or ""

    if evidence.intent is DimensionalityIntent.UNSPECIFIED:
        spec.structure_type = proposed if proposed is not None else StructureType.PRATT
        # Not added to `specified`: the dimensional choice was ours, so it
        # stays disclosed as an assumption by _record_defaults.
        spec.note_default(
            f"structural system: {'spatial (3D)' if spec.structure_type.is_spatial else 'planar (2D)'} "
            f"— {evidence.describe()}, so this dimensionality was assumed, not requested"
        )
        return

    wants_spatial = bool(evidence.spatial_terms)
    if wants_spatial:
        resolved = StructureType.SPACE_TRUSS
    else:
        # Prefer the AI's planar suggestion when it is genuinely planar and
        # consistent with the text; otherwise read the type name directly.
        resolved = (
            proposed
            if proposed is not None and not proposed.is_spatial
            else _named_planar_type(text)
        )

    if proposed is not None and proposed is not resolved:
        spec.note_default(
            f"structure type: AI proposed '{proposed.value}', overridden to "
            f"'{resolved.value}' by the requirement text ({evidence.describe()})"
        )

    if evidence.intent is DimensionalityIntent.CONFLICTING:
        spec.note_default(
            f"structural system: requirement states both — {evidence.describe()}. "
            f"Selected '{resolved.value}' because a 3D term was present; "
            f"this reading is not certain."
        )

    spec.structure_type = resolved
    specified.add("structure_type")


def _record_defaults(spec: EngineeringSpec, specified: set[str]) -> None:
    """Attach a human-readable note for every value the user did not specify."""
    values = {
        "structure_type": spec.structure_type.value,
        "span": f"{spec.span:g} m",
        "height": f"{spec.height:g} m",
        "num_panels": str(spec.num_panels),
        "primary_load": f"{spec.primary_load / 1000:g} kN",
        "material_key": spec.material_key,
        "section_key": spec.section_key,
        "safety_factor": f"{spec.safety_factor:g}",
        "max_displacement_ratio": f"L/{spec.max_displacement_ratio:g}",
        "load_description": spec.load_description,
    }
    if spec.structure_type.is_spatial:
        values["width"] = f"{spec.width:g} m"

    for field_name, shown in values.items():
        if field_name not in specified:
            label = _DEFAULT_MESSAGES.get(field_name, field_name)
            spec.note_default(f"{label}: {shown} (not specified — default applied)")


async def parse_requirements_ai(raw_input: str) -> EngineeringSpec:
    """
    Parse natural language requirements using Gemini API.

    Falls back to rule-based parsing if API is unavailable.
    """
    if not GEMINI_API_KEY:
        return parse_requirements_fallback(raw_input)

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{EXTRACTION_PROMPT}\n\nUser requirement:\n{raw_input}",
        )

        # Extract JSON from response
        text = response.text.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)

        data = json.loads(text)
        return _build_spec_from_dict(data, raw_input)

    except Exception as e:
        print(f"AI parsing failed: {e}, falling back to rule-based parser")
        return parse_requirements_fallback(raw_input)


def parse_requirements_fallback(raw_input: str) -> EngineeringSpec:
    """
    Rule-based fallback parser for when the AI is unavailable.

    Extracts numbers and keywords from the input string.
    """
    text = raw_input.lower()
    spec = EngineeringSpec(raw_input=raw_input)
    specified: set[str] = set()

    # --- Structure type (checked first: it determines whether width matters) ---
    _resolve_structure_type(spec, detect_dimensionality(raw_input), specified)

    # --- Width / depth (transverse, z direction) ---
    width_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:m|meter|metres|meters)?\s*(?:wide|width|deep|depth)'
        r'|(?:width|wide|depth|deep)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:m|meter)',
        text,
    )
    if width_match:
        spec.width = float(width_match.group(1) or width_match.group(2))
        specified.add("width")

    # --- Span ---
    span_patterns = [
        r'(?:span|length|long)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:m|meter)',
        r'(\d+(?:\.\d+)?)\s*(?:m|meter|metres|meters)[\s-]*(?:span|long|bridge|truss|pedestrian)',
        r'(\d+(?:\.\d+)?)\s*(?:-\s*)?(?:m|meter)\s',
    ]
    for pattern in span_patterns:
        match = re.search(pattern, text)
        if match:
            candidate = float(match.group(1))
            # Don't mistake the width phrase for the span.
            if not (specified and "width" in specified and abs(candidate - spec.width) < 1e-9):
                spec.span = candidate
                specified.add("span")
                break

    # --- Vertical load (kN or N) ---
    load_patterns = [
        r'(\d+(?:\.\d+)?)\s*kn',
        r'(\d+(?:\.\d+)?)\s*kilo\s*newton',
        r'(\d+(?:\.\d+)?)\s*n(?:ewton)?(?:\s|$)',
    ]
    for i, pattern in enumerate(load_patterns):
        match = re.search(pattern, text)
        if match:
            val = float(match.group(1))
            if i < 2:  # kN patterns
                val *= 1000
            spec.primary_load = val
            specified.add("primary_load")
            break

    # --- Lateral (transverse / wind) load ---
    wind_match = re.search(
        r'(?:wind|lateral|transverse|crosswind)\s*(?:load\s*)?(?:of\s*)?(\d+(?:\.\d+)?)\s*(kn|n)\b'
        r'|(\d+(?:\.\d+)?)\s*(kn|n)\s*(?:wind|lateral|transverse)',
        text,
    )
    if wind_match:
        value = wind_match.group(1) or wind_match.group(3)
        unit = wind_match.group(2) or wind_match.group(4)
        spec.lateral_load_z = float(value) * (1000 if unit == 'kn' else 1)
        specified.add("lateral_load_z")

    # --- Structural depth (height, y direction) ---
    height_match = re.search(r'height\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:m|meter)', text)
    if height_match:
        spec.height = float(height_match.group(1))
        specified.add("height")
    else:
        spec.height = spec.span / 6  # default ratio

    # --- Load distribution ---
    if 'distribut' in text or 'uniform' in text:
        spec.load_description = "distributed load"
        specified.add("load_description")
    elif 'center' in text or 'centre' in text or 'middle' in text:
        spec.load_description = "center point load"
        specified.add("load_description")
    else:
        spec.load_description = "center point load"

    # --- Material ---
    if 'a992' in text:
        spec.material_key = "A992"
        specified.add("material_key")
    elif 'aluminum' in text or 'aluminium' in text or '6061' in text:
        spec.material_key = "AL6061"
        specified.add("material_key")
    elif 'a36' in text or 'steel' in text:
        spec.material_key = "A36"
        specified.add("material_key")
    else:
        spec.material_key = "A36"

    # --- Panel count ---
    panels_match = re.search(r'(\d+)\s*panel', text)
    if panels_match:
        spec.num_panels = int(panels_match.group(1))
        specified.add("num_panels")
    else:
        if spec.span <= 15:
            spec.num_panels = 6
        elif spec.span <= 30:
            spec.num_panels = 8
        else:
            spec.num_panels = 10

    # A space truss needs a real width — derive one only if not given.
    if spec.structure_type.is_spatial and spec.width <= 0:
        spec.width = round(spec.span / 5, 3)

    spec.description = raw_input.strip()
    _record_defaults(spec, specified)
    return spec


def _build_spec_from_dict(data: dict, raw_input: str) -> EngineeringSpec:
    """Build an EngineeringSpec from a parsed dictionary."""
    type_map = {
        "pratt": StructureType.PRATT,
        "warren": StructureType.WARREN,
        "howe": StructureType.HOWE,
        "space_truss": StructureType.SPACE_TRUSS,
    }

    structure_type = type_map.get(data.get("structure_type", "pratt"), StructureType.PRATT)
    span = float(data.get("span", 20.0))

    spec = EngineeringSpec(
        structure_type=structure_type,
        span=span,
        height=float(data.get("height", span / 6)),
        width=float(data.get("width", 0.0) or 0.0),
        num_panels=int(data.get("num_panels", 6)),
        primary_load=float(data.get("primary_load", 50000)),
        lateral_load_x=float(data.get("lateral_load_x", 0.0) or 0.0),
        lateral_load_z=float(data.get("lateral_load_z", 0.0) or 0.0),
        load_description=data.get("load_description", "center point load"),
        material_key=data.get("material_key", "A36"),
        safety_factor=float(data.get("safety_factor", 1.67)),
        max_displacement_ratio=float(data.get("max_displacement_ratio", 300)),
        description=data.get("description", raw_input),
        section_key=data.get("section_key", "CHS_114x6"),
        raw_input=raw_input,
    )

    specified = set(data.get("specified_fields") or [])

    # The AI's structure_type is a proposal, not the verdict: the requirement
    # text is re-read deterministically so an AI guess can never turn an
    # explicit 3D request into a planar model (or the reverse).
    _resolve_structure_type(
        spec, detect_dimensionality(raw_input), specified, proposed=structure_type,
    )

    # A space truss needs a real width — derive one only if the model didn't give one.
    if spec.structure_type.is_spatial and spec.width <= 0:
        spec.width = round(spec.span / 5, 3)

    # Phase 14: disclose everything the user did not explicitly state.
    _record_defaults(spec, specified)
    return spec
