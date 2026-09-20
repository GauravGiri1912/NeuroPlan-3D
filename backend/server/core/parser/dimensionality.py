"""
NeuroPlan-3D — Structural Dimensionality Intent Detection

Deterministic, rule-based detection of whether a requirement asks for a
PLANAR (2D) or SPATIAL (3D) structural system. No AI is involved: this is
the authoritative reading of what the user literally wrote, and it is
applied on top of the AI parser's answer so an AI guess can never silently
downgrade an explicit 3D request to a planar model.

The detector reports the terms it matched rather than only a verdict, so
the resolution can be disclosed as evidence instead of asserted.
"""
import re
from dataclasses import dataclass

from ...models.structure import DimensionalityIntent

# Terms that state a three-dimensional structural system. Ordered longest
# first only for readability — matching is independent per pattern.
_SPATIAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("three dimensional", r"three[\s-]*dimension(?:al|s)?"),
    ("3d", r"\b3\s*-?\s*d\b"),
    ("space truss", r"space[\s-]*truss"),
    ("space frame", r"space[\s-]*frame"),
    ("spatial truss", r"spatial[\s-]*truss"),
    ("spatial", r"\bspatial\b"),
    ("box truss", r"box[\s-]*truss"),
)

# Terms that state a two-dimensional (planar) structural system.
_PLANAR_PATTERNS: tuple[tuple[str, str], ...] = (
    ("two dimensional", r"two[\s-]*dimension(?:al|s)?"),
    ("2d", r"\b2\s*-?\s*d\b"),
    ("planar", r"\bplanar\b"),
    ("plane truss", r"plane[\s-]*truss"),
)

# Naming a planar truss type is itself a statement of dimensionality: every
# one of these generators lays every node out at z = 0.
_PLANAR_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("pratt", r"\bpratt\b"),
    ("warren", r"\bwarren\b"),
    ("howe", r"\bhowe\b"),
)


@dataclass(frozen=True)
class DimensionalityEvidence:
    """What the text actually said about dimensionality, and the verdict."""
    intent: DimensionalityIntent
    spatial_terms: tuple[str, ...]
    planar_terms: tuple[str, ...]

    @property
    def matched_terms(self) -> tuple[str, ...]:
        return self.spatial_terms + self.planar_terms

    def describe(self) -> str:
        """Human-readable evidence line — quotes the terms, never paraphrases."""
        if self.intent is DimensionalityIntent.UNSPECIFIED:
            return "no 2D/3D term found in the requirement"
        parts = []
        if self.spatial_terms:
            parts.append("3D terms: " + ", ".join(f"'{t}'" for t in self.spatial_terms))
        if self.planar_terms:
            parts.append("2D/planar terms: " + ", ".join(f"'{t}'" for t in self.planar_terms))
        return "; ".join(parts)


def _matches(text: str, patterns: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(label for label, pattern in patterns if re.search(pattern, text))


def detect_dimensionality(raw_input: str) -> DimensionalityEvidence:
    """
    Classify the dimensional intent of a natural-language requirement.

    EXPLICIT_SPATIAL  — only 3D terms present.
    EXPLICIT_PLANAR   — only 2D/planar terms (or a planar truss type) present.
    CONFLICTING       — both present ("3D Pratt truss", "2D space truss").
    UNSPECIFIED       — neither; the caller must not claim certainty.
    """
    text = (raw_input or "").lower()

    spatial = _matches(text, _SPATIAL_PATTERNS)
    planar = _matches(text, _PLANAR_PATTERNS) + _matches(text, _PLANAR_TYPE_PATTERNS)

    if spatial and planar:
        intent = DimensionalityIntent.CONFLICTING
    elif spatial:
        intent = DimensionalityIntent.EXPLICIT_SPATIAL
    elif planar:
        intent = DimensionalityIntent.EXPLICIT_PLANAR
    else:
        intent = DimensionalityIntent.UNSPECIFIED

    return DimensionalityEvidence(
        intent=intent, spatial_terms=spatial, planar_terms=planar,
    )
