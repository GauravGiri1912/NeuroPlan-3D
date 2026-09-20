/**
 * NeuroPlan-3D — Result Provenance
 *
 * Answers "where did this number come from?" for every headline metric.
 * Each entry names the element that produced it, the equation, and the
 * actual input values — and clicking it opens that element in the
 * Inspector, so the chain from number to physical source is navigable.
 *
 * The values shown are the solver's own; this component performs no
 * physical calculation.
 */
import { useState } from 'react';
import { useAppStore } from '../stores/appStore';
import type { ProvenanceData } from '../types/engineering';

function formatValue(p: ProvenanceData): string {
  // Display-friendly units. The underlying SI value is always shown in the
  // expanded detail so nothing is hidden by the conversion.
  switch (p.units) {
    case 'Pa': return `${(p.value / 1e6).toFixed(3)} MPa`;
    case 'm': return `${(p.value * 1000).toFixed(3)} mm`;
    case 'N': return `${(p.value / 1000).toFixed(3)} kN`;
    case 'kg': return `${p.value.toFixed(1)} kg`;
    case '–': return p.value.toFixed(4);
    default: return `${p.value.toPrecision(6)} ${p.units}`;
  }
}

export default function ProvenancePanel() {
  const evidence = useAppStore((s) => s.evidence);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const inspect = useAppStore((s) => s.inspect);
  const [open, setOpen] = useState<string | null>(null);

  if (pipelineStage !== 'complete' || !evidence) return null;

  return (
    <div className="panel-section">
      <div className="panel-section-header">
        <span className="panel-section-title">Result Provenance</span>
        <span style={{ fontSize: 9, color: '#5c6370' }}>where each number came from</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {evidence.provenance.map((p) => {
          const isOpen = open === p.metric;
          const canInspect = p.source_id !== null &&
            (p.source_type === 'member' || p.source_type === 'node' || p.source_type === 'reaction');
          return (
            <div key={p.metric}>
              <div
                onClick={() => setOpen(isOpen ? null : p.metric)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline',
                  gap: 8,
                  cursor: 'pointer',
                  fontSize: 11,
                  fontFamily: "'JetBrains Mono', monospace",
                  padding: '2px 0',
                }}
                title="Show calculation"
              >
                <span style={{ color: '#8b919e' }}>{isOpen ? '▾' : '▸'} {p.label}</span>
                <span style={{ color: '#e1e4ea', fontWeight: 600, whiteSpace: 'nowrap' }}>
                  {formatValue(p)}
                </span>
              </div>

              {isOpen && (
                <div style={{
                  margin: '3px 0 6px 12px',
                  padding: '6px 8px',
                  background: '#12141a',
                  border: '1px solid #2a2d38',
                  borderRadius: 3,
                  fontSize: 10,
                  lineHeight: 1.6,
                  color: '#8b919e',
                  fontFamily: "'JetBrains Mono', monospace",
                }}>
                  <div>
                    <span style={{ color: '#5c6370' }}>Source: </span>
                    {canInspect ? (
                      <span
                        style={{ color: '#3b82f6', cursor: 'pointer' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          inspect(
                            p.source_type === 'reaction' ? 'node' : (p.source_type as 'node' | 'member'),
                            p.source_id as number,
                          );
                        }}
                        title="Open in Inspector"
                      >
                        {p.source_detail} ↗
                      </span>
                    ) : p.source_detail}
                  </div>
                  {p.equation && (
                    <div style={{ marginTop: 3 }}>
                      <span style={{ color: '#5c6370' }}>Equation: </span>
                      <span style={{ color: '#b8bdc7' }}>{p.equation}</span>
                    </div>
                  )}
                  {p.inputs.length > 0 && (
                    <div style={{ marginTop: 3 }}>
                      <span style={{ color: '#5c6370' }}>Inputs:</span>
                      {p.inputs.map((i, k) => (
                        <div key={k} style={{ paddingLeft: 8 }}>
                          {i.label} = {Math.abs(i.value) >= 1e5 || (i.value !== 0 && Math.abs(i.value) < 1e-3)
                            ? i.value.toExponential(5)
                            : i.value.toPrecision(6)} {i.units}
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ marginTop: 3 }}>
                    <span style={{ color: '#5c6370' }}>SI value: </span>
                    {p.value.toExponential(6)} {p.units}
                  </div>
                  {p.note && (
                    <div style={{ marginTop: 3, color: '#f59e0b' }}>{p.note}</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
