/**
 * NeuroPlan-3D — Engineering Credibility Panel
 *
 * Every check is expandable into the evidence that produced it: the actual
 * value, the limit it was compared against, the units, and its source.
 * A status is never shown without that evidence behind it.
 *
 * Statuses are deliberately four-valued. NOT_AVAILABLE exists so a
 * capability the system does not have (real-world validation) is stated
 * plainly rather than quietly omitted or counted as a pass.
 */
import { useState } from 'react';
import { useAppStore } from '../stores/appStore';
import type { CheckStatus, VerificationItemData } from '../types/engineering';

const CATEGORY_LABELS: Record<string, string> = {
  model_definition: 'Model Definition',
  solver: 'Solver Verification',
  equilibrium: 'Equilibrium',
  numerical: 'Numerical Convergence',
  limits: 'Structural Limit Checks',
  benchmark: 'Benchmark / Independent Checks',
  real_world: 'Real-World Validation',
};

const CATEGORY_ORDER = [
  'model_definition', 'solver', 'equilibrium',
  'numerical', 'limits', 'real_world',
];

function statusColor(status: CheckStatus): string {
  switch (status) {
    case 'pass': return '#22c55e';
    case 'fail': return '#ef4444';
    case 'not_available': return '#f59e0b';
    default: return '#8b919e';
  }
}

function statusLabel(status: CheckStatus): string {
  switch (status) {
    case 'pass': return 'PASS';
    case 'fail': return 'FAIL';
    case 'not_available': return 'N/A';
    default: return 'INFO';
  }
}

export default function CredibilityPanel() {
  const evidence = useAppStore((s) => s.evidence);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const [openSection, setOpenSection] = useState<string | null>(null);

  if (pipelineStage !== 'complete' || !evidence) return null;

  const byCategory = new Map<string, VerificationItemData[]>();
  for (const item of evidence.verification) {
    const list = byCategory.get(item.category) ?? [];
    list.push(item);
    byCategory.set(item.category, list);
  }

  const toggle = (key: string) => setOpenSection(openSection === key ? null : key);

  return (
    <div className="panel-section">
      <div className="panel-section-header">
        <span className="panel-section-title">Engineering Credibility</span>
        <span style={{
          fontSize: 10,
          color: evidence.computation_verified ? '#22c55e' : '#ef4444',
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {evidence.computation_verified ? 'COMPUTATION VERIFIED' : 'CHECKS FAILED'}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {CATEGORY_ORDER.filter((c) => byCategory.has(c)).map((category) => {
          const items = byCategory.get(category)!;
          const hasFail = items.some((i) => i.status === 'fail');
          const hasNA = items.some((i) => i.status === 'not_available');
          const summary: CheckStatus = hasFail ? 'fail' : hasNA ? 'not_available' : 'pass';
          const isOpen = openSection === category;

          return (
            <div key={category}>
              <div
                onClick={() => toggle(category)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  cursor: 'pointer',
                  padding: '4px 6px',
                  background: isOpen ? '#1e2028' : 'transparent',
                  borderRadius: 3,
                  fontSize: 11,
                  fontFamily: "'JetBrains Mono', monospace",
                }}
                title="Click to see the evidence"
              >
                <span style={{ color: '#b8bdc7' }}>
                  {isOpen ? '▾' : '▸'} {CATEGORY_LABELS[category] ?? category}
                </span>
                <span style={{ color: statusColor(summary), fontWeight: 600 }}>
                  {statusLabel(summary)}
                </span>
              </div>

              {isOpen && (
                <div style={{
                  padding: '6px 8px 8px 16px',
                  borderLeft: '2px solid #2a2d38',
                  marginLeft: 6,
                }}>
                  {items.map((item) => (
                    <EvidenceRow key={item.key} item={item} />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Benchmarks — run live against hand-derived reference values */}
        <BenchmarkSection
          isOpen={openSection === 'benchmark'}
          onToggle={() => toggle('benchmark')}
        />

        {/* Assumptions & limitations */}
        <AssumptionsSection
          isOpen={openSection === 'assumptions'}
          onToggle={() => toggle('assumptions')}
        />

        {/* Simulation record */}
        <RecordSection
          isOpen={openSection === 'record'}
          onToggle={() => toggle('record')}
        />
      </div>
    </div>
  );
}

function EvidenceRow({ item }: { item: VerificationItemData }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ marginBottom: 5 }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 8,
          cursor: 'pointer',
          fontSize: 10,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        <span style={{ color: '#8b919e' }}>{item.label}</span>
        <span style={{ color: statusColor(item.status), fontWeight: 600, whiteSpace: 'nowrap' }}>
          {statusLabel(item.status)}
        </span>
      </div>
      <div style={{ fontSize: 10, color: '#5c6370', fontFamily: "'JetBrains Mono', monospace" }}>
        {item.actual_display}
        {item.limit_display && item.limit_display !== '–' && (
          <span style={{ color: '#3f4450' }}>  ·  limit {item.limit_display}</span>
        )}
      </div>
      {expanded && (
        <div style={{
          marginTop: 4,
          padding: '6px 8px',
          background: '#12141a',
          border: '1px solid #2a2d38',
          borderRadius: 3,
          fontSize: 10,
          lineHeight: 1.6,
          color: '#8b919e',
        }}>
          <div><strong style={{ color: '#b8bdc7' }}>Source:</strong> {item.source}</div>
          {item.detail && <div style={{ marginTop: 3 }}>{item.detail}</div>}
        </div>
      )}
    </div>
  );
}

function BenchmarkSection({ isOpen, onToggle }: { isOpen: boolean; onToggle: () => void }) {
  const evidence = useAppStore((s) => s.evidence);
  if (!evidence) return null;
  const allPass = evidence.benchmarks.every((b) => b.status === 'pass');

  return (
    <div>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          cursor: 'pointer', padding: '4px 6px',
          background: isOpen ? '#1e2028' : 'transparent',
          borderRadius: 3, fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
        }}
        title="Independent checks against values derived by hand"
      >
        <span style={{ color: '#b8bdc7' }}>
          {isOpen ? '▾' : '▸'} Benchmark / Independent Checks
        </span>
        <span style={{ color: allPass ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
          {allPass ? 'PASS' : 'FAIL'}
        </span>
      </div>
      {isOpen && (
        <div style={{ padding: '6px 8px 8px 16px', borderLeft: '2px solid #2a2d38', marginLeft: 6 }}>
          {evidence.benchmarks.map((b, i) => (
            <div key={i} style={{ marginBottom: 8, fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
              <div style={{ color: '#b8bdc7' }}>{b.quantity}</div>
              <div style={{ color: '#5c6370' }}>{b.case}</div>
              <div style={{ color: '#8b919e', marginTop: 2 }}>
                NeuroPlan {b.neuroplan_value.toPrecision(7)} {b.units}
              </div>
              <div style={{ color: '#8b919e' }}>
                Reference {b.reference_value.toPrecision(7)} {b.units}
              </div>
              <div style={{
                color: b.status === 'pass' ? '#22c55e' : '#ef4444',
                fontWeight: 600,
              }}>
                Δ {b.absolute_difference.toExponential(2)} · rel {(b.relative_difference * 100).toExponential(2)}%
                {'  '}[{b.status.toUpperCase()}]
              </div>
              <div style={{ color: '#5c6370', marginTop: 2 }}>{b.reference_source}</div>
              {b.derivation && (
                <details style={{ marginTop: 2 }}>
                  <summary style={{ cursor: 'pointer', color: '#3b82f6' }}>Derivation</summary>
                  <div style={{ color: '#8b919e', marginTop: 2 }}>{b.derivation}</div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AssumptionsSection({ isOpen, onToggle }: { isOpen: boolean; onToggle: () => void }) {
  const evidence = useAppStore((s) => s.evidence);
  if (!evidence) return null;
  const notModeled = evidence.assumptions.filter((a) => !a.modeled);

  return (
    <div>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          cursor: 'pointer', padding: '4px 6px',
          background: isOpen ? '#1e2028' : 'transparent',
          borderRadius: 3, fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        <span style={{ color: '#b8bdc7' }}>
          {isOpen ? '▾' : '▸'} Assumptions & Limitations
        </span>
        <span style={{ color: '#f59e0b', fontWeight: 600 }}>
          {notModeled.length} NOT MODELED
        </span>
      </div>
      {isOpen && (
        <div style={{ padding: '6px 8px 8px 16px', borderLeft: '2px solid #2a2d38', marginLeft: 6 }}>
          <div style={{ fontSize: 10, color: '#22c55e', marginBottom: 3 }}>MODELED</div>
          {evidence.assumptions.filter((a) => a.modeled).map((a, i) => (
            <div key={i} style={{ fontSize: 10, color: '#8b919e', marginBottom: 4 }}>
              ✓ <strong style={{ color: '#b8bdc7' }}>{a.topic}</strong> — {a.description}
              {a.implication && <div style={{ color: '#5c6370' }}>{a.implication}</div>}
            </div>
          ))}
          <div style={{ fontSize: 10, color: '#f59e0b', margin: '8px 0 3px' }}>NOT MODELED</div>
          {notModeled.map((a, i) => (
            <div key={i} style={{ fontSize: 10, color: '#8b919e', marginBottom: 4 }}>
              ✕ <strong style={{ color: '#b8bdc7' }}>{a.topic}</strong> — {a.description}
              {a.implication && <div style={{ color: '#5c6370' }}>{a.implication}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RecordSection({ isOpen, onToggle }: { isOpen: boolean; onToggle: () => void }) {
  const evidence = useAppStore((s) => s.evidence);
  if (!evidence) return null;
  const r = evidence.record;

  const rows: [string, string][] = [
    ['Simulation ID', r.simulation_id],
    ['Timestamp (UTC)', r.timestamp_utc],
    ['Software version', r.software_version],
    ['Solver method', r.solver_method],
    ['Solver backend', r.solver_backend],
    ['Nodes / Members', `${r.node_count} / ${r.member_count}`],
    ['DOF', `${r.total_dof} (${r.dof_per_node} per node)`],
    ['Supports / Loads', `${r.support_count} / ${r.load_count}`],
    ['Materials', r.material_keys.join(', ')],
    ['Sections', r.section_keys.join(', ')],
    ['Iterations', `${r.iteration_count}`],
  ];

  return (
    <div>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          cursor: 'pointer', padding: '4px 6px',
          background: isOpen ? '#1e2028' : 'transparent',
          borderRadius: 3, fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        <span style={{ color: '#b8bdc7' }}>{isOpen ? '▾' : '▸'} Simulation Record</span>
        <span style={{ color: '#8b919e', fontSize: 9 }}>{r.simulation_id.slice(0, 8)}</span>
      </div>
      {isOpen && (
        <div style={{ padding: '6px 8px 8px 16px', borderLeft: '2px solid #2a2d38', marginLeft: 6 }}>
          {rows.map(([k, v]) => (
            <div key={k} style={{
              display: 'flex', justifyContent: 'space-between', gap: 8,
              fontSize: 10, fontFamily: "'JetBrains Mono', monospace", padding: '1px 0',
            }}>
              <span style={{ color: '#5c6370', whiteSpace: 'nowrap' }}>{k}</span>
              <span style={{ color: '#8b919e', textAlign: 'right' }}>{v}</span>
            </div>
          ))}
          {r.warnings.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 10, color: '#f59e0b' }}>WARNINGS</div>
              {r.warnings.map((w, i) => (
                <div key={i} style={{ fontSize: 10, color: '#8b919e' }}>• {w}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
