/**
 * NeuroPlan-3D — Failure Lab
 *
 * Remove one member from the currently loaded structure and re-run the
 * real production solver (server.core.experiments.engine.run_experiment
 * via POST /api/engineering/experiments/member-removal). Every number
 * shown comes from that response — nothing is computed or guessed here.
 *
 * After a successful experiment, Structural Autopsy is fetched from
 * POST /api/engineering/experiments/member-removal/autopsy, which
 * serializes server.core.experiments.autopsy.diagnose() directly — no
 * diagnosis text is constructed in this file, and no AI/LLM is involved.
 *
 * Also includes a manual "Re-analyze Design" control (MEMBER_AREA_SCALE
 * only): scales one member's area on the ORIGINAL structure and
 * re-solves via POST /api/engineering/experiments/member-area-scale. It
 * is a single, standalone, isolated change — never compounded with the
 * removal experiment above, and never automatic. No AI suggestion, no
 * optimization, no "best" repair is chosen — see Task 7 spec.
 *
 * Scope: MEMBER_REMOVE and single-member MEMBER_AREA_SCALE only. No
 * Load Path Explorer, no robustness sweeps, no automatic repair.
 */
import { useState } from 'react';
import { useAppStore } from '../stores/appStore';
import type { MemberData, SpecData } from '../types/engineering';

const API_BASE = '/api';
const MONO = "'JetBrains Mono', monospace";

interface CaseSummary {
  max_displacement_mm: number;
  max_stress_mpa: number;
  critical_member: number | null;
  verified: boolean;
}

interface MemberRemovalResponse {
  removed_member_id: number;
  baseline_status: 'stable' | 'solved_but_failed_checks' | 'unstable';
  structural_status: 'stable' | 'solved_but_failed_checks' | 'unstable';
  baseline: CaseSummary;
  perturbed: CaseSummary | null;
  displacement_change_mm: number | null;
  displacement_percent_change: number | null;
  stress_change_mpa: number | null;
  stress_percent_change: number | null;
  critical_member_changed: boolean;
  error: string | null;
}

type EvidenceValue = string | number | boolean | null;

interface DiagnosisStep {
  type: string;
  summary: string;
  evidence: Record<string, EvidenceValue>;
}

interface StructuralAutopsyResponse {
  removed_member_id: number | null;
  baseline_status: string;
  perturbed_status: string;
  steps: DiagnosisStep[];
  cause_attribution: string;
  limitation_note: string;
}

const STATUS_LABEL: Record<string, string> = {
  stable: 'STABLE',
  solved_but_failed_checks: 'SOLVED — CHECKS FAILED',
  unstable: 'UNSTABLE (MECHANISM)',
};

const STATUS_COLOR: Record<string, string> = {
  stable: '#22c55e',
  solved_but_failed_checks: '#f59e0b',
  unstable: '#ef4444',
};

const STEP_LABEL: Record<string, string> = {
  structural_instability: 'Structural instability detected',
  force_redistribution: 'Member force redistribution detected',
  critical_member_changed: 'Critical member changed',
  stress_increase: 'Stress increase',
  stress_decrease: 'Stress decrease',
  stress_unchanged: 'Stress unchanged',
  displacement_increase: 'Displacement increase',
  displacement_decrease: 'Displacement decrease',
  displacement_unchanged: 'Displacement unchanged',
  failed_check: 'Failure criterion triggered',
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail ? String(data.detail) : `HTTP ${res.status}`);
  }
  return data as T;
}

function pct(value: number | null): string {
  if (value === null) return '— (baseline ≈ 0)';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export default function FailureLabPanel() {
  const [open, setOpen] = useState(true);
  const [memberId, setMemberId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MemberRemovalResponse | null>(null);

  const [autopsy, setAutopsy] = useState<StructuralAutopsyResponse | null>(null);
  const [autopsyLoading, setAutopsyLoading] = useState(false);
  const [autopsyError, setAutopsyError] = useState<string | null>(null);

  const spec = useAppStore((s) => s.spec);
  const currentStructure = useAppStore((s) => s.currentStructure);
  const setFailureLabMember = useAppStore((s) => s.setFailureLabMember);

  const structure = currentStructure();
  const members = structure?.members ?? [];

  const selectMember = (id: number | null) => {
    setMemberId(id);
    setFailureLabMember(id);
    setResult(null);
    setError(null);
    setAutopsy(null);
    setAutopsyError(null);
  };

  const run = async () => {
    if (memberId === null) return;
    setLoading(true);
    setError(null);
    setAutopsy(null);
    setAutopsyError(null);
    let succeeded = false;
    try {
      const data = await post<MemberRemovalResponse>('/engineering/experiments/member-removal', {
        spec, member_id: memberId,
      });
      setResult(data);
      succeeded = true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setResult(null);
    }
    setLoading(false);

    // Autopsy is fetched separately, AFTER the experiment result is shown —
    // its own failure must never hide the already-successful experiment.
    if (succeeded) {
      setAutopsyLoading(true);
      try {
        const data = await post<StructuralAutopsyResponse>(
          '/engineering/experiments/member-removal/autopsy', { spec, member_id: memberId }
        );
        setAutopsy(data);
      } catch (e) {
        setAutopsyError(e instanceof Error ? e.message : 'Unknown error');
      }
      setAutopsyLoading(false);
    }
  };

  return (
    <div className="panel-section">
      <div
        className="panel-section-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen(!open)}
      >
        <span className="panel-section-title">{open ? '▾' : '▸'} Failure Lab</span>
        <span style={{ fontSize: 9, color: '#5c6370' }}>member removal experiment</span>
      </div>

      {open && (
        <div style={{ fontSize: 11, fontFamily: MONO }}>
          {!structure && (
            <div style={{ color: '#8b919e' }}>
              No structure loaded. Run a pipeline first.
            </div>
          )}

          {structure && (
            <>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                <select
                  value={memberId ?? ''}
                  onChange={(e) => selectMember(e.target.value === '' ? null : Number(e.target.value))}
                  style={{
                    fontFamily: MONO, fontSize: 10, background: '#1e2028', color: '#b8bdc7',
                    border: '1px solid #2a2d38', borderRadius: 3, flex: 1,
                  }}
                >
                  <option value="">Select member…</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      M{m.id} ({m.node_i} → {m.node_j})
                    </option>
                  ))}
                </select>
                <button
                  className="run-action-button"
                  onClick={run}
                  disabled={memberId === null || loading}
                  style={{
                    fontFamily: MONO, fontSize: 10,
                    cursor: memberId === null || loading ? 'default' : 'pointer',
                    background: '#1e2028', color: '#3b82f6', border: '1px solid #3b82f6',
                    borderRadius: 3, padding: '3px 10px', opacity: memberId === null ? 0.5 : 1,
                  }}
                >
                  {loading ? 'Running…' : 'Remove Member'}
                </button>
              </div>

              {memberId === null && !error && (
                <div style={{ color: '#5c6370' }}>Select a member to enable the experiment.</div>
              )}

              {error && <div style={{ color: '#ef4444', marginBottom: 6 }}>{error}</div>}

              {result && <ResultView result={result} />}

              {result && <BeforeAfterTable result={result} />}

              {result && (
                <AutopsySection
                  autopsy={autopsy}
                  loading={autopsyLoading}
                  error={autopsyError}
                />
              )}

              <ReanalyzeSection members={members} spec={spec} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ResultView({ result }: { result: MemberRemovalResponse }) {
  const statusColor = STATUS_COLOR[result.structural_status] ?? '#8b919e';
  const statusLabel = STATUS_LABEL[result.structural_status] ?? result.structural_status;

  return (
    <div style={{ lineHeight: 1.6 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 6px', background: '#1e2028', borderRadius: 3, marginBottom: 6,
      }}>
        <span style={{ color: '#b8bdc7' }}>Member {result.removed_member_id} removed</span>
        <span style={{ color: statusColor, fontWeight: 600, fontSize: 10 }}>{statusLabel}</span>
      </div>

      <Section title="BASELINE">
        <Row label="Max displacement" value={`${result.baseline.max_displacement_mm.toFixed(3)} mm`} />
        <Row label="Max stress" value={`${result.baseline.max_stress_mpa.toFixed(2)} MPa`} />
        <Row label="Critical member" value={String(result.baseline.critical_member ?? '—')} />
        <Row label="Verified" value={result.baseline.verified ? 'PASS' : 'FAIL'}
             color={result.baseline.verified ? '#22c55e' : '#ef4444'} />
      </Section>

      {result.perturbed && (
        <Section title="AFTER MEMBER REMOVAL">
          <Row label="Max displacement" value={`${result.perturbed.max_displacement_mm.toFixed(3)} mm`} />
          <Row label="Max stress" value={`${result.perturbed.max_stress_mpa.toFixed(2)} MPa`} />
          <Row label="Critical member" value={String(result.perturbed.critical_member ?? '—')}
               color={result.critical_member_changed ? '#f59e0b' : undefined} />
          <Row label="Verified" value={result.perturbed.verified ? 'PASS' : 'FAIL'}
               color={result.perturbed.verified ? '#22c55e' : '#ef4444'} />
        </Section>
      )}

      {result.perturbed ? (
        <Section title="DELTA">
          <Row label="Displacement change" value={`${result.displacement_change_mm!.toFixed(3)} mm`} />
          <Row label="Displacement %" value={pct(result.displacement_percent_change)} />
          <Row label="Stress change" value={`${result.stress_change_mpa!.toFixed(2)} MPa`} />
          <Row label="Stress %" value={pct(result.stress_percent_change)} />
        </Section>
      ) : (
        <Section title="RESULT">
          <div style={{ color: '#ef4444', marginBottom: 4 }}>
            The perturbed structure is UNSTABLE — no displacement or stress
            values were computed (none are fabricated).
          </div>
          {result.error && (
            <div style={{
              color: '#8b919e', whiteSpace: 'pre-wrap', fontSize: 9,
              maxHeight: 160, overflowY: 'auto', border: '1px solid #2a2d38',
              borderRadius: 3, padding: 4,
            }}>
              {result.error}
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

/**
 * Compact Before/After comparison table. All values come directly from
 * the member-removal response — no recomputation, no independent
 * percentage calculation. Percentages are shown exactly as the backend
 * returns them (null -> "—", never re-derived here).
 */
function BeforeAfterTable({ result }: { result: MemberRemovalResponse }) {
  const after = result.perturbed;

  return (
    <Section title="BEFORE / AFTER COMPARISON">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
        <thead>
          <tr style={{ color: '#5c6370', textAlign: 'left' }}>
            <th></th><th>BASELINE</th><th>AFTER</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderTop: '1px solid #2a2d38' }}>
            <td style={{ color: '#5c6370' }}>Max displacement</td>
            <td style={{ color: '#b8bdc7' }}>{result.baseline.max_displacement_mm.toFixed(3)} mm</td>
            <td style={{ color: '#b8bdc7' }}>
              {after ? `${after.max_displacement_mm.toFixed(3)} mm` : '—'}
            </td>
          </tr>
          <tr>
            <td style={{ color: '#5c6370' }}>Max stress</td>
            <td style={{ color: '#b8bdc7' }}>{result.baseline.max_stress_mpa.toFixed(2)} MPa</td>
            <td style={{ color: '#b8bdc7' }}>
              {after ? `${after.max_stress_mpa.toFixed(2)} MPa` : '—'}
            </td>
          </tr>
          <tr>
            <td style={{ color: '#5c6370' }}>Critical member</td>
            <td style={{ color: '#b8bdc7' }}>
              {result.baseline.critical_member !== null ? `M${result.baseline.critical_member}` : '—'}
            </td>
            <td style={{ color: result.critical_member_changed ? '#f59e0b' : '#b8bdc7' }}>
              {after && after.critical_member !== null ? `M${after.critical_member}` : '—'}
            </td>
          </tr>
          <tr>
            <td style={{ color: '#5c6370' }}>Status</td>
            <td style={{ color: STATUS_COLOR[result.baseline_status] ?? '#8b919e' }}>
              {STATUS_LABEL[result.baseline_status] ?? result.baseline_status}
            </td>
            <td style={{ color: STATUS_COLOR[result.structural_status] ?? '#8b919e' }}>
              {STATUS_LABEL[result.structural_status] ?? result.structural_status}
            </td>
          </tr>
        </tbody>
      </table>

      {after ? (
        <div style={{ marginTop: 6 }}>
          <div style={{ color: '#5c6370', fontSize: 9, marginBottom: 2 }}>DELTA</div>
          <Row label="Displacement" value={deltaText(result.displacement_change_mm, result.displacement_percent_change, 'mm')} />
          <Row label="Stress" value={deltaText(result.stress_change_mpa, result.stress_percent_change, 'MPa')} />
        </div>
      ) : (
        <div style={{ color: '#ef4444', marginTop: 6, fontSize: 10 }}>
          UNSTABLE / MECHANISM — the perturbed structure could not be
          solved, so no displacement or stress values exist to compare.
        </div>
      )}
    </Section>
  );
}

/** Formats a backend-provided delta/percentage pair. Never recomputes either value. */
function deltaText(change: number | null, percent: number | null, unit: string): string {
  if (change === null) return '—';
  const sign = change >= 0 ? '+' : '';
  const magnitude = `${sign}${change.toFixed(unit === 'mm' ? 3 : 2)} ${unit}`;
  const pctText = percent === null
    ? '— (baseline ≈ 0)'
    : `${percent >= 0 ? '+' : ''}${percent.toFixed(1)}%`;
  return `${magnitude} (${pctText})`;
}

function AutopsySection({ autopsy, loading, error }: {
  autopsy: StructuralAutopsyResponse | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Section title="STRUCTURAL AUTOPSY">
      {loading && <div style={{ color: '#8b919e' }}>Running diagnosis…</div>}

      {error && (
        <div style={{ color: '#f59e0b' }}>
          Autopsy unavailable: {error}
          <div style={{ color: '#5c6370', fontSize: 9, marginTop: 2 }}>
            The experiment result above is unaffected.
          </div>
        </div>
      )}

      {!loading && !error && autopsy && autopsy.steps.length === 0 && (
        <div style={{ color: '#5c6370' }}>No diagnosis steps were produced for this result.</div>
      )}

      {!loading && !error && autopsy && autopsy.steps.length > 0 && (
        <>
          <Row label="Status" value={`${autopsy.baseline_status.toUpperCase()} → ${autopsy.perturbed_status.toUpperCase()}`} />
          <div style={{ marginTop: 4 }}>
            {autopsy.steps.map((step, i) => (
              <DiagnosisStepView key={i} index={i + 1} step={step} />
            ))}
          </div>
          <div style={{
            marginTop: 6, padding: '4px 6px', background: '#1e2028', borderRadius: 3,
          }}>
            <div style={{ color: '#f59e0b', fontWeight: 600, fontSize: 10 }}>
              CAUSE NOT DETERMINED
            </div>
            <div style={{ color: '#8b919e', fontSize: 9, marginTop: 2 }}>
              {autopsy.cause_attribution === 'CAUSE_NOT_DETERMINED'
                ? 'The available solver results do not establish a specific causal mechanism.'
                : autopsy.cause_attribution}
            </div>
            <div style={{ color: '#5c6370', fontSize: 9, marginTop: 4 }}>
              {autopsy.limitation_note}
            </div>
          </div>
        </>
      )}
    </Section>
  );
}

function DiagnosisStepView({ index, step }: { index: number; step: DiagnosisStep }) {
  const label = STEP_LABEL[step.type] ?? step.type;
  const evidenceEntries = Object.entries(step.evidence);

  return (
    <div style={{ marginBottom: 6, paddingLeft: 4, borderLeft: '2px solid #2a2d38' }}>
      <div style={{ color: '#b8bdc7' }}>
        <span style={{ color: '#3b82f6' }}>{String(index).padStart(2, '0')}</span>{'  '}{label}
      </div>
      {step.summary !== label && (
        <div style={{ color: '#8b919e', fontSize: 9, marginLeft: 20 }}>{step.summary}</div>
      )}
      {evidenceEntries.length > 0 && (
        <div style={{ marginLeft: 20, marginTop: 2 }}>
          {evidenceEntries.map(([key, value]) => (
            <EvidenceRow key={key} evidenceKey={key} value={value} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceRow({ evidenceKey, value }: { evidenceKey: string; value: EvidenceValue }) {
  // COMPUTED = a direct solver output. DERIVED = calculated from other
  // computed values (percentage changes). No ASSUMED/MEASURED/NOT_MODELED
  // values occur in this feature's evidence — none are invented here.
  const tag = evidenceKey.includes('percent') ? 'DERIVED' : 'COMPUTED';
  const tagColor = tag === 'DERIVED' ? '#8b5cf6' : '#3b82f6';

  let display: string;
  if (value === null) {
    display = '—';
  } else if (typeof value === 'number') {
    display = Number.isInteger(value) ? String(value) : value.toFixed(3);
  } else {
    display = String(value);
  }

  const isLong = display.length > 60;

  return (
    <div style={{ display: 'flex', gap: 6, fontSize: 9, marginBottom: 1, alignItems: 'flex-start' }}>
      <span style={{ color: tagColor, whiteSpace: 'nowrap', minWidth: 62 }}>[{tag}]</span>
      <span style={{ color: '#5c6370', whiteSpace: 'nowrap' }}>{evidenceKey}:</span>
      <span style={{
        color: '#8b919e', whiteSpace: isLong ? 'pre-wrap' : 'nowrap',
        maxHeight: isLong ? 140 : undefined, overflowY: isLong ? 'auto' : undefined,
      }}>
        {display}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
      <div style={{ color: '#5c6370', marginBottom: 2, fontSize: 9, letterSpacing: 0.5 }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#5c6370', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ color: color ?? '#b8bdc7', textAlign: 'right' }}>{value}</span>
    </div>
  );
}

// ───────────────────────── Re-analyze Design (manual MEMBER_AREA_SCALE) ─────────────────────────

interface MemberAreaScaleResponse {
  member_id: number;
  scale_factor: number;
  baseline_status: 'stable' | 'solved_but_failed_checks' | 'unstable';
  structural_status: 'stable' | 'solved_but_failed_checks' | 'unstable';
  baseline: CaseSummary;
  perturbed: CaseSummary | null;
  displacement_change_mm: number | null;
  displacement_percent_change: number | null;
  stress_change_mpa: number | null;
  stress_percent_change: number | null;
  critical_member_changed: boolean;
  error: string | null;
}

// Deliberately different wording from STATUS_LABEL elsewhere — the task
// asks specifically for this vocabulary here, avoiding "PASS/FAIL" and
// any "safe/optimized/best/fixed" language.
const REANALYZE_STATUS_LABEL: Record<string, string> = {
  stable: 'Passed configured checks',
  solved_but_failed_checks: 'Failed configured checks',
  unstable: 'Unstable',
};

const SCALE_FACTOR_PRESETS = [1.05, 1.10, 1.20];

function ReanalyzeSection({ members, spec }: { members: MemberData[]; spec: SpecData | null }) {
  const [memberId, setMemberId] = useState<number | null>(null);
  const [scaleFactor, setScaleFactor] = useState<number>(1.10);
  const [customScale, setCustomScale] = useState<string>('');
  const [useCustom, setUseCustom] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MemberAreaScaleResponse | null>(null);

  const effectiveScale = useCustom ? Number(customScale) : scaleFactor;
  const canRun = memberId !== null && Number.isFinite(effectiveScale) && effectiveScale > 0;

  const run = async () => {
    if (!canRun) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await post<MemberAreaScaleResponse>('/engineering/experiments/member-area-scale', {
        spec, member_id: memberId, scale_factor: effectiveScale,
      });
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    }
    setLoading(false);
  };

  if (members.length === 0) return null;

  return (
    <div style={{ borderTop: '1px solid #2a2d38', marginTop: 8, paddingTop: 6 }}>
      <div style={{ color: '#b8bdc7', marginBottom: 4 }}>Re-analyze Design</div>
      <div style={{ color: '#5c6370', fontSize: 9, marginBottom: 6 }}>
        Scale one member's cross-sectional area on the original structure
        and re-solve. A single, standalone, isolated change — never
        combined with the member-removal experiment above.
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
        <span style={{ color: '#5c6370', fontSize: 9 }}>Member:</span>
        <select
          value={memberId ?? ''}
          onChange={(e) => { setMemberId(e.target.value === '' ? null : Number(e.target.value)); setResult(null); setError(null); }}
          style={{
            fontFamily: MONO, fontSize: 10, background: '#1e2028', color: '#b8bdc7',
            border: '1px solid #2a2d38', borderRadius: 3,
          }}
        >
          <option value="">Select…</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>M{m.id} ({m.node_i} → {m.node_j})</option>
          ))}
        </select>

        <span style={{ color: '#5c6370', fontSize: 9 }}>Area ×</span>
        {SCALE_FACTOR_PRESETS.map((s) => (
          <button
            key={s}
            onClick={() => { setUseCustom(false); setScaleFactor(s); setResult(null); }}
            style={{
              fontFamily: MONO, fontSize: 10, cursor: 'pointer', borderRadius: 3, padding: '2px 8px',
              background: !useCustom && scaleFactor === s ? '#3b82f6' : '#1e2028',
              color: !useCustom && scaleFactor === s ? '#0a0b0f' : '#8b919e',
              border: '1px solid #3b82f6',
            }}
          >
            {s.toFixed(2)}
          </button>
        ))}
        <input
          type="number" min="0.01" step="0.01" placeholder="custom"
          value={customScale}
          onChange={(e) => { setUseCustom(true); setCustomScale(e.target.value); setResult(null); }}
          style={{
            width: 60, fontFamily: MONO, fontSize: 10, background: '#1e2028', color: '#b8bdc7',
            border: `1px solid ${useCustom ? '#3b82f6' : '#2a2d38'}`, borderRadius: 3, padding: '2px 4px',
          }}
        />
      </div>

      <button
        onClick={run}
        disabled={!canRun || loading}
        style={{
          fontFamily: MONO, fontSize: 10, cursor: !canRun || loading ? 'default' : 'pointer',
          background: '#1e2028', color: '#3b82f6', border: '1px solid #3b82f6',
          borderRadius: 3, padding: '3px 10px', opacity: canRun ? 1 : 0.5, marginBottom: 6,
        }}
      >
        {loading ? 'Re-analyzing…' : 'Re-analyze'}
      </button>

      {error && <div style={{ color: '#ef4444', marginBottom: 6 }}>{error}</div>}

      {result && <ReanalyzeResultView result={result} />}
    </div>
  );
}

function ReanalyzeResultView({ result }: { result: MemberAreaScaleResponse }) {
  const after = result.perturbed;

  return (
    <div style={{ lineHeight: 1.6 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 6px', background: '#1e2028', borderRadius: 3, marginBottom: 6,
      }}>
        <span style={{ color: '#b8bdc7' }}>M{result.member_id} area × {result.scale_factor.toFixed(2)}</span>
        <span style={{
          color: STATUS_COLOR[result.structural_status] ?? '#8b919e', fontWeight: 600, fontSize: 10,
        }}>
          {REANALYZE_STATUS_LABEL[result.structural_status] ?? result.structural_status}
        </span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
        <thead>
          <tr style={{ color: '#5c6370', textAlign: 'left' }}>
            <th></th><th>ORIGINAL</th><th>REPAIRED / MODIFIED</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderTop: '1px solid #2a2d38' }}>
            <td style={{ color: '#5c6370' }}>Max displacement</td>
            <td style={{ color: '#b8bdc7' }}>{result.baseline.max_displacement_mm.toFixed(3)} mm</td>
            <td style={{ color: '#b8bdc7' }}>{after ? `${after.max_displacement_mm.toFixed(3)} mm` : '—'}</td>
          </tr>
          <tr>
            <td style={{ color: '#5c6370' }}>Max stress</td>
            <td style={{ color: '#b8bdc7' }}>{result.baseline.max_stress_mpa.toFixed(2)} MPa</td>
            <td style={{ color: '#b8bdc7' }}>{after ? `${after.max_stress_mpa.toFixed(2)} MPa` : '—'}</td>
          </tr>
          <tr>
            <td style={{ color: '#5c6370' }}>Critical member</td>
            <td style={{ color: '#b8bdc7' }}>
              {result.baseline.critical_member !== null ? `M${result.baseline.critical_member}` : '—'}
            </td>
            <td style={{ color: result.critical_member_changed ? '#f59e0b' : '#b8bdc7' }}>
              {after && after.critical_member !== null ? `M${after.critical_member}` : '—'}
            </td>
          </tr>
          <tr>
            <td style={{ color: '#5c6370' }}>Status</td>
            <td style={{ color: STATUS_COLOR[result.baseline_status] ?? '#8b919e' }}>
              {REANALYZE_STATUS_LABEL[result.baseline_status] ?? result.baseline_status}
            </td>
            <td style={{ color: STATUS_COLOR[result.structural_status] ?? '#8b919e' }}>
              {REANALYZE_STATUS_LABEL[result.structural_status] ?? result.structural_status}
            </td>
          </tr>
        </tbody>
      </table>

      {after ? (
        <div style={{ marginTop: 6 }}>
          <div style={{ color: '#5c6370', fontSize: 9, marginBottom: 2 }}>DELTA</div>
          <Row label="Displacement" value={deltaText(result.displacement_change_mm, result.displacement_percent_change, 'mm')} />
          <Row label="Stress" value={deltaText(result.stress_change_mpa, result.stress_percent_change, 'MPa')} />
          <div style={{ color: '#5c6370', fontSize: 9, marginTop: 4 }}>
            Re-analyzed against the original design. Both metrics are shown
            regardless of direction — no automatic judgement is made about
            whether this change is an improvement.
          </div>
        </div>
      ) : (
        <div style={{ color: '#ef4444', marginTop: 6, fontSize: 10 }}>
          UNSTABLE / MECHANISM — the modified structure could not be
          solved, so no displacement or stress values exist to compare.
        </div>
      )}
    </div>
  );
}
