/**
 * NeuroPlan-3D — Analysis Model Badge
 *
 * Shows which structure an analysis response actually ran on, read
 * verbatim from the response's `model` field (see backend
 * engineering_routes._model_meta) — never inferred or recomputed here.
 * Used by every engineering-analysis module so a result can never be
 * mistaken for having analyzed a different structure than intended.
 */
import type { AnalysisModelMeta } from '../types/engineering';

const TYPE_LABEL: Record<string, string> = {
  pratt: 'Pratt Truss',
  howe: 'Howe Truss',
  warren: 'Warren Truss',
  space_truss: 'Space Truss',
};

export default function AnalysisModelBadge({ model }: { model?: AnalysisModelMeta }) {
  if (!model) return null;

  const label = TYPE_LABEL[model.structure_type] ?? model.structure_type;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '5px 8px', marginBottom: 10,
      background: model.spec_provided ? '#12241a' : '#3a2b1f',
      border: `1px solid ${model.spec_provided ? '#1f4a2e' : '#6b4a15'}`,
      borderRadius: 3, fontSize: 10,
      fontFamily: "'JetBrains Mono', monospace",
    }}>
      <span style={{ color: model.spec_provided ? '#22c55e' : '#f59e0b', fontWeight: 600 }}>
        {model.spec_provided ? 'ANALYZING CURRENT MODEL' : 'NO CURRENT MODEL — BACKEND DEFAULT USED'}
      </span>
      <span style={{ color: '#8b919e' }}>
        {label} ({model.is_spatial ? '3D' : '2D'}) · {model.node_count} nodes · {model.member_count} members
      </span>
    </div>
  );
}
