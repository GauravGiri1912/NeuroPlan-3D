/**
 * NeuroPlan-3D — Structural Model / Dimensionality Transparency Card
 *
 * Surfaces server.core.parser.dimensionality's verdict (spec.dimensionality_intent)
 * plainly: whether 2D/3D was explicitly requested, left unspecified (a
 * default was assumed), or the requirement text conflicted with itself.
 * Never claims certainty the backend did not report, and never recomputes
 * the classification — it only renders spec.dimensionality_intent and the
 * defaults_applied note the parser already attached.
 *
 * "Evidence" is the requirement text itself (quoted verbatim) plus the
 * disclosure note the parser recorded — nothing here re-derives which
 * words matched, since that would duplicate parser logic in the frontend.
 */
import { useAppStore } from '../stores/appStore';
import type { SpecData, StructureData, AnalysisResultsData } from '../types/engineering';

const TYPE_LABEL: Record<string, string> = {
  pratt: 'PRATT TRUSS',
  howe: 'HOWE TRUSS',
  warren: 'WARREN TRUSS',
  space_truss: 'SPACE TRUSS',
};

const INTENT_META: Record<string, { label: string; color: string }> = {
  explicit_spatial: { label: '✓ Explicitly requested', color: '#22c55e' },
  explicit_planar: { label: '✓ Explicitly requested', color: '#22c55e' },
  conflicting: {
    label: '⚠ Requirement contains conflicting terminology — interpretation is not certain',
    color: '#f59e0b',
  },
  unspecified: {
    label: '⚠ Dimensionality not specified. The system selected the default representation.',
    color: '#f59e0b',
  },
};

export default function StructuralModelCard({ spec, structure, results }: {
  spec: SpecData;
  structure?: StructureData | null;
  results?: AnalysisResultsData | null;
}) {
  const setActiveNavView = useAppStore((s) => s.setActiveNavView);

  const spatial = spec.is_spatial ?? spec.structure_type === 'space_truss';
  const intent = spec.dimensionality_intent ?? 'unspecified';
  const meta = INTENT_META[intent] ?? INTENT_META.unspecified;
  const typeLabel = TYPE_LABEL[spec.structure_type] ?? spec.structure_type.toUpperCase();

  // The disclosure note the parser itself recorded, when there is one
  // (override / conflict / unspecified cases carry one; a clean explicit
  // match does not, since nothing needed disclosing).
  const structuralNote = (spec.defaults_applied ?? []).find(
    (n) => n.startsWith('structural system:') || n.startsWith('structure type:'),
  );

  const zExtent = structure && structure.nodes.length > 0
    ? Math.max(...structure.nodes.map((n) => n.z)) - Math.min(...structure.nodes.map((n) => n.z))
    : null;

  return (
    <div className="view-section">
      <div className="section-title">Structural Model</div>
      <div style={{
        padding: '10px 14px',
        background: '#1a1c24',
        border: '1px solid #2a2d38',
        borderRadius: 4,
      }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: '#e1e4ea', letterSpacing: 0.3 }}>
          {typeLabel} ({spatial ? '3D' : '2D'})
        </div>
        <div style={{ fontSize: 11, color: meta.color, marginTop: 4 }}>
          {meta.label}
        </div>

        {structuralNote && (
          <div style={{ fontSize: 10, color: '#8b919e', marginTop: 6, lineHeight: 1.5 }}>
            {structuralNote}
          </div>
        )}

        {spec.raw_input?.trim() && (
          <div style={{ fontSize: 10, color: '#5c6370', marginTop: 6, fontStyle: 'italic' }}>
            Requirement: "{spec.raw_input.trim()}"
          </div>
        )}

        {structure && (
          <div style={{
            display: 'flex', gap: 16, marginTop: 10, paddingTop: 8,
            borderTop: '1px solid #2a2d38', fontFamily: "'JetBrains Mono', monospace",
            fontSize: 10, color: '#8b919e',
          }}>
            <span>{structure.nodes.length} nodes</span>
            <span>{structure.members.length} members</span>
            {results && <span>{results.dof_count} DOF</span>}
            {spatial && zExtent !== null && <span>Z extent: {zExtent.toFixed(2)} m</span>}
          </div>
        )}

        {intent === 'unspecified' && (
          <button
            className="btn btn-sm"
            style={{ marginTop: 10 }}
            onClick={() => setActiveNavView('setup')}
          >
            Adjust in New Analysis →
          </button>
        )}
      </div>
    </div>
  );
}
