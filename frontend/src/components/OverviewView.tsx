/**
 * NeuroPlan-3D — Engineering Summary (Overview)
 *
 * A presentation layer ONLY. Every value here is read from state the
 * application already holds — the current spec, structure, solver
 * results, the /analyse engineering report, the evidence package and the
 * validation-library record. Nothing on this page performs an
 * engineering calculation, and nothing is fabricated: where a capability
 * has not been run, it says so rather than implying a result.
 *
 * The one figure that is NOT live is the automated-test count, which is
 * a recorded snapshot (see RECORDED_TEST_SUITE) and is labelled as such
 * in the UI with the command to reproduce it.
 */
import { useEffect, useState } from 'react';
import { useAppStore, type NavView } from '../stores/appStore';
import StructuralViewport from './StructuralViewport';
import StructuralModelCard from './StructuralModelCard';
import type { EngineeringAnalysisData, AnalysisResultsData } from '../types/engineering';

const STRUCTURE_LABEL: Record<string, string> = {
  pratt: 'Pratt Truss (2D)',
  howe: 'Howe Truss (2D)',
  warren: 'Warren Truss (2D)',
  space_truss: 'Box Space Truss (3D)',
};

const VALIDATION_STATE_LABEL: Record<string, string> = {
  not_available: 'NOT AVAILABLE',
  reference_available: 'REFERENCE AVAILABLE',
  reference_compared: 'REFERENCE COMPARED',
  criterion_met: 'CRITERION MET',
  criterion_not_met: 'CRITERION NOT MET',
  model_not_applicable: 'MODEL NOT APPLICABLE',
};

const VALIDATION_STATE_COLOR: Record<string, string> = {
  not_available: '#5c6370',
  reference_available: '#8b919e',
  reference_compared: '#3b82f6',
  criterion_met: '#22c55e',
  criterion_not_met: '#ef4444',
  model_not_applicable: '#f59e0b',
};

/**
 * Recorded backend test-suite result — a snapshot, not a live metric.
 * Kept in one place and shown with its reproduction command so it can
 * never be mistaken for something this page verified itself.
 */
const RECORDED_TEST_SUITE = { passing: 621, command: 'pytest -q (backend/)' };

/** Honest per-capability state vocabulary — never "PASS" for merely existing. */
type CoverageState =
  | 'RUN' | 'COMPLETED' | 'PASS' | 'FAIL' | 'REVIEW'
  | 'SCREENING' | 'AVAILABLE' | 'NOT MODELED' | 'NOT RUN';

const COVERAGE_COLOR: Record<CoverageState, string> = {
  RUN: '#22c55e',
  COMPLETED: '#22c55e',
  PASS: '#22c55e',
  FAIL: '#ef4444',
  REVIEW: '#f59e0b',
  SCREENING: '#3b82f6',
  AVAILABLE: '#8b919e',
  'NOT MODELED': '#5c6370',
  'NOT RUN': '#5c6370',
};

interface CoverageItem {
  label: string;
  state: CoverageState;
  detail: string;
  view: NavView;
}

/**
 * Derives each capability's state from data the app already has.
 * `engineering` is the /analyse report (null until it has been fetched);
 * `results` is the pipeline solver result.
 */
function buildCoverage(
  engineering: EngineeringAnalysisData | null,
  results: AnalysisResultsData | null,
  selfWeight: boolean,
  thermalDeltaT: number,
): { group: string; items: CoverageItem[] }[] {
  const buckling = engineering?.buckling;
  const code = engineering?.code_checks;
  const connections = engineering?.connections;
  const stability = engineering?.stability;

  return [
    {
      group: 'Structural Analysis',
      items: [
        {
          label: 'Linear Static', view: 'results',
          state: results ? 'COMPLETED' : 'NOT RUN',
          detail: results ? `${results.dof_count} DOF · direct stiffness` : 'Run an analysis',
        },
        {
          label: 'Self Weight', view: 'load-cases',
          state: engineering ? (selfWeight ? 'RUN' : 'AVAILABLE') : 'AVAILABLE',
          detail: engineering
            ? (selfWeight ? 'Included in combination' : 'Excluded by user')
            : 'Open Load Cases to evaluate',
        },
        {
          label: 'Load Cases', view: 'load-cases',
          state: engineering?.load_summary ? 'COMPLETED' : 'AVAILABLE',
          detail: engineering?.load_summary?.combination_name ?? 'Named combinations',
        },
        {
          label: 'Nonlinear', view: 'advanced',
          state: 'AVAILABLE', detail: 'P-Delta / material — run on demand',
        },
      ],
    },
    {
      group: 'Dynamic / Response',
      items: [
        { label: 'Modal', view: 'advanced', state: 'AVAILABLE', detail: 'Eigenvalue modes — run on demand' },
        { label: 'Seismic', view: 'advanced', state: 'AVAILABLE', detail: 'IS 1893 response spectrum' },
      ],
    },
    {
      group: 'Stability',
      items: [
        {
          label: 'Diagnostics', view: 'diagnostics',
          state: stability ? 'COMPLETED' : 'AVAILABLE',
          detail: stability ? stability.determinacy : 'Determinacy & load path',
        },
        {
          label: 'Buckling', view: 'buckling',
          state: buckling
            ? (buckling.n_failed > 0 ? 'FAIL' : buckling.n_unconservative > 0 ? 'REVIEW' : 'SCREENING')
            : 'SCREENING',
          detail: buckling
            ? `${buckling.n_compression} compression · ${buckling.n_failed} over Euler`
            : 'Euler screening',
        },
      ],
    },
    {
      group: 'Design Screening',
      items: [
        {
          label: 'IS 800', view: 'is800',
          state: code ? (code.n_failed > 0 ? 'FAIL' : 'SCREENING') : 'SCREENING',
          detail: code
            ? `${code.n_failed} failed · max D/C ${code.max_dc_ratio.toFixed(2)}`
            : 'Screening subset, not compliance',
        },
        {
          label: 'Connections', view: 'load-cases',
          state: connections
            ? (connections.n_failed > 0 ? 'FAIL'
              : connections.governing_member_id !== null ? 'SCREENING' : 'NOT MODELED')
            : 'SCREENING',
          detail: connections
            ? `${connections.members_without_connection.length} members undeclared`
            : 'Bolt / weld screening',
        },
      ],
    },
    {
      group: 'Environment',
      items: [
        {
          label: 'Thermal', view: 'load-cases',
          state: thermalDeltaT !== 0 ? 'RUN' : 'AVAILABLE',
          detail: thermalDeltaT !== 0 ? `ΔT = ${thermalDeltaT} K applied` : 'Set ΔT in Load Cases',
        },
        { label: 'Fire', view: 'advanced', state: 'AVAILABLE', detail: 'Elevated-temperature strength' },
      ],
    },
    {
      group: 'Durability',
      items: [
        { label: 'Fatigue', view: 'advanced', state: 'AVAILABLE', detail: 'S-N screening — needs detail category' },
      ],
    },
    {
      group: 'Support / Boundary',
      items: [
        { label: 'Springs', view: 'advanced', state: 'AVAILABLE', detail: 'Elastic support stiffness' },
        { label: 'Settlement', view: 'load-cases', state: 'NOT MODELED', detail: 'No API surface exposed' },
      ],
    },
    {
      group: 'Investigation',
      items: [
        { label: 'Failure Lab', view: 'failure-lab', state: 'AVAILABLE', detail: 'Remove · autopsy · repair' },
        { label: 'Robustness', view: 'robustness', state: 'AVAILABLE', detail: 'Deterministic load scales' },
        { label: 'Sensitivity', view: 'sensitivity', state: 'AVAILABLE', detail: 'One-at-a-time perturbation' },
      ],
    },
  ];
}

export default function OverviewView() {
  const spec = useAppStore((s) => s.spec);
  const structure = useAppStore((s) => s.currentStructure());
  const results = useAppStore((s) => s.currentResults());
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const validationResult = useAppStore((s) => s.validationResult);
  const validationLoading = useAppStore((s) => s.validationLoading);
  const fetchValidation = useAppStore((s) => s.fetchValidation);
  const engineering = useAppStore((s) => s.engineering);
  const engineeringSelfWeight = useAppStore((s) => s.engineeringSelfWeight);
  const engineeringThermalRef = useAppStore((s) => s.engineeringThermalRef);
  const fetchEngineering = useAppStore((s) => s.fetchEngineering);
  const evidence = useAppStore((s) => s.evidence);
  const verificationStatus = useAppStore((s) => s.verificationStatus);
  const setActiveNavView = useAppStore((s) => s.setActiveNavView);

  const [showLimitations, setShowLimitations] = useState(false);

  useEffect(() => {
    fetchValidation();
  }, [fetchValidation]);

  // Same cached store action the Engineering panels use — so the summary
  // shows the real screening states instead of a permanent "AVAILABLE".
  useEffect(() => {
    if (structure) fetchEngineering();
  }, [structure, fetchEngineering]);

  if (pipelineStage === 'idle' || !structure) {
    return (
      <div className="view-content">
        <div className="empty-state" style={{ height: '70vh' }}>
          <div className="empty-state-icon">◇</div>
          <div className="empty-state-text" style={{ maxWidth: 320 }}>
            No structure has been generated yet.
            <br /><br />
            Go to <strong>New Analysis</strong> to describe a structure or
            run a demo preset — the AI proposes a specification, the real
            Direct Stiffness Method solver decides whether it stands.
          </div>
          <button className="btn btn-primary" onClick={() => setActiveNavView('setup')}>
            ▸ New Analysis
          </button>
        </div>
      </div>
    );
  }

  const diagnosis = results?.diagnosis;
  const maxStressMpa = results
    ? Math.max(0, ...results.member_results.map((m) => m.stress_mpa))
    : null;
  const criticalMember = results
    ? results.member_results.reduce((critical, member) => (
      !critical || Math.abs(member.stress_mpa) > Math.abs(critical.stress_mpa) ? member : critical
    ), results.member_results[0] ?? null)
    : null;
  const analysisStatus = pipelineStage === 'complete'
    ? (verificationStatus === 'pass' ? 'CHECKS PASSED' : verificationStatus === 'fail' ? 'CHECKS FAILED' : 'ANALYSIS COMPLETE')
    : pipelineStage.replace('_', ' ').toUpperCase();
  const spatial = spec?.is_spatial ?? spec?.structure_type === 'space_truss';
  const record = evidence?.record ?? null;
  const coverage = buildCoverage(engineering, results, engineeringSelfWeight, engineeringThermalRef);

  const benchmarksPassed = evidence?.benchmarks.filter((b) => b.status === 'pass').length ?? 0;
  const benchmarkTotal = evidence?.benchmarks.length ?? 0;
  const verificationPassed = evidence?.verification.filter((v) => v.status === 'pass').length ?? 0;
  const verificationFailed = evidence?.verification.filter((v) => v.status === 'fail').length ?? 0;
  const verificationTotal = evidence?.verification.length ?? 0;
  // Items that are neither pass nor fail (informational, or not available —
  // e.g. real-world validation) are counted separately: reporting them as
  // "not passed" would imply failures that did not occur.
  const verificationOther = verificationTotal - verificationPassed - verificationFailed;

  return (
    <div className="view-content">
      <div className="view-header">
        <div className="text-label">Engineering Summary</div>
        <h1 className="view-title">
          {spec?.description?.trim() || STRUCTURE_LABEL[spec?.structure_type ?? ''] || 'Untitled Structure'}
        </h1>
        <div className="view-subtitle">
          {STRUCTURE_LABEL[spec?.structure_type ?? ''] ?? spec?.structure_type}
          {' · '}{structure.members.length} members{' · '}{structure.nodes.length} nodes
        </div>
      </div>

      <div className="overview-commandbar">
        <div>
          <div className="commandbar-label">CURRENT MODEL</div>
          <div className="commandbar-title">{spec?.description?.trim() || 'Loaded structural model'}</div>
          <div className="commandbar-meta">
            {spatial ? '3D' : '2D'} · {structure.nodes.length} nodes · {structure.members.length} members
            {results ? ` · ${results.dof_count} DOF` : ''}
            {spec?.material_key ? ` · ${spec.material_key}` : ''}
            {spec?.section_key ? ` · ${spec.section_key}` : ''}
          </div>
          <div className="commandbar-meta">
            {engineering?.load_summary?.combination_name ?? 'Load combination — open Load Cases'}
          </div>
        </div>
        <div className={`status-chip ${verificationStatus}`}>
          <span className="status-chip-dot" />
          {analysisStatus}
        </div>
      </div>

      {/* AI proposes. Physics decides. — the product's core claim as a chain. */}
      <div className="workflow-strip" aria-label="AI proposes, physics decides">
        {[
          { step: 'AI Proposal', done: !!spec },
          { step: 'Deterministic Physics', done: !!results },
          { step: 'Engineering Checks', done: !!engineering },
          { step: 'Evidence', done: !!evidence },
          { step: 'Report', done: pipelineStage === 'complete' },
        ].map(({ step, done }, index) => (
          <div className={`workflow-step ${done ? 'complete' : ''}`} key={step}>
            <span className="workflow-index">{String(index + 1).padStart(2, '0')}</span>
            <span>{step}</span>
          </div>
        ))}
      </div>
      <div className="section-helper" style={{ marginTop: 6 }}>
        AI proposes. Physics decides — the AI only interprets the requirement;
        every number below comes from the deterministic solver.
      </div>

      <div className="overview-preview">
        <StructuralViewport />
      </div>

      {spec && (
        <StructuralModelCard spec={spec} structure={structure} results={results} />
      )}

      <section className="view-section">
        <div className="section-title">Key Results</div>
        {results ? (
          <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="metric-card">
              <div className="metric-label">Maximum Displacement</div>
              <div className="metric-value">
                {diagnosis?.max_displacement_mm.toFixed(2)}
                <span className="metric-unit">mm</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Maximum Stress</div>
              <div className="metric-value">
                {maxStressMpa?.toFixed(1)}
                <span className="metric-unit">MPa</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Critical Member</div>
              <div className="metric-value">{criticalMember ? `M${criticalMember.member_id}` : '—'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Configured Checks</div>
              <div className="metric-value" style={{
                color: diagnosis ? (diagnosis.passed ? '#22c55e' : '#ef4444') : undefined,
              }}>
                {diagnosis ? (diagnosis.passed ? 'PASS' : 'FAIL') : 'NOT RUN'}
              </div>
            </div>
          </div>
        ) : (
          <div className="summary-notrun">NOT RUN — no solver result for this model yet.</div>
        )}
      </section>

      {record && (
        <section className="view-section">
          <div className="section-title">Analysis Record</div>
          <div className="summary-kv-grid">
            <SummaryKV label="Solver" value={record.solver_method} />
            <SummaryKV label="Backend" value={record.solver_backend} />
            <SummaryKV label="Total DOF" value={`${record.total_dof}`} />
            <SummaryKV label="Material" value={record.material_keys.join(', ') || '—'} />
            <SummaryKV label="Section" value={record.section_keys.join(', ') || '—'} />
            <SummaryKV label="Supports / Loads" value={`${record.support_count} / ${record.load_count}`} />
            <SummaryKV label="Iterations" value={`${record.iteration_count}`} />
            <SummaryKV label="Simulation ID" value={record.simulation_id.slice(0, 8)} />
          </div>
        </section>
      )}

      <section className="view-section">
        <div className="section-heading-row">
          <div>
            <div className="section-title">Engineering Analysis Coverage</div>
            <div className="section-helper">
              What exists, and what has actually been run on this model. A capability
              is never marked PASS merely because it is implemented.
            </div>
          </div>
          <span className="eyebrow-tag">CLICK TO OPEN</span>
        </div>
        {coverage.map(({ group, items }) => (
          <div key={group} className="coverage-group">
            <div className="coverage-group-title">{group}</div>
            <div className="coverage-row">
              {items.map((item) => (
                <button
                  key={item.label}
                  className="coverage-item"
                  onClick={() => setActiveNavView(item.view)}
                >
                  <span className="coverage-item-label">{item.label}</span>
                  <span className="coverage-item-detail">{item.detail}</span>
                  <span className="coverage-item-state" style={{ color: COVERAGE_COLOR[item.state] }}>
                    {item.state}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="view-section">
        <div className="section-title">Engineering Verification</div>
        <div className="summary-kv-grid">
          <SummaryKV
            label="Automated Tests"
            value={`${RECORDED_TEST_SUITE.passing} PASSING`}
            note={`recorded — reproduce with ${RECORDED_TEST_SUITE.command}`}
            color="#22c55e"
          />
          <SummaryKV
            label="Analytical Benchmarks"
            value={benchmarkTotal ? `${benchmarksPassed}/${benchmarkTotal} MATCHED` : 'NOT RUN'}
            note={benchmarkTotal ? 'computed live against closed-form references' : undefined}
            color={benchmarkTotal && benchmarksPassed === benchmarkTotal ? '#22c55e' : '#8b919e'}
          />
          <SummaryKV
            label="Verification Checks"
            value={verificationTotal
              ? `${verificationPassed} PASSED · ${verificationFailed} FAILED`
              : 'NOT RUN'}
            note={verificationTotal
              ? `equilibrium, geometry, limits — this run${verificationOther ? ` · ${verificationOther} informational / not available` : ''}`
              : undefined}
            color={!verificationTotal ? '#8b919e' : verificationFailed === 0 ? '#22c55e' : '#ef4444'}
          />
          <SummaryKV
            label="Computation"
            value={evidence ? (evidence.computation_verified ? 'VERIFIED' : 'NOT VERIFIED') : 'NOT RUN'}
            note="numerical model only — not real-world safety"
            color={evidence?.computation_verified ? '#22c55e' : '#f59e0b'}
          />
          <SummaryKV
            label="Experimental Reference"
            value={validationResult
              ? (VALIDATION_STATE_LABEL[validationResult.state] ?? validationResult.state)
              : (validationLoading ? 'LOADING…' : 'NOT LOADED')}
            note="see Validation for the full comparison"
            color={validationResult ? (VALIDATION_STATE_COLOR[validationResult.state] ?? '#8b919e') : '#8b919e'}
          />
          <SummaryKV
            label="IS 800 / Buckling / Connections"
            value="SCREENING"
            note="screening subsets — not code compliance"
            color="#3b82f6"
          />
        </div>
        <div className="section-helper" style={{ marginTop: 8 }}>
          Independent experimental validation is not claimed.
        </div>
      </section>

      <section className="view-section">
        <div className="section-title">Validation Status</div>
        {validationLoading && !validationResult && (
          <div style={{ color: '#5c6370', fontSize: 12 }}>Loading validation record…</div>
        )}
        {validationResult && (
          <div
            className="verification-badge"
            style={{
              background: '#22262e',
              borderLeft: `3px solid ${VALIDATION_STATE_COLOR[validationResult.state] ?? '#8b919e'}`,
              color: VALIDATION_STATE_COLOR[validationResult.state] ?? '#8b919e',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: 4,
            }}
          >
            <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>
              {VALIDATION_STATE_LABEL[validationResult.state] ?? validationResult.state}
            </span>
            <span style={{ fontSize: 11, fontWeight: 400, color: '#8b919e' }}>
              {validationResult.independence.headline}
            </span>
          </div>
        )}
      </section>

      <section className="view-section">
        <div
          className="section-title"
          style={{ cursor: 'pointer', color: '#3b82f6' }}
          onClick={() => setShowLimitations(!showLimitations)}
        >
          {showLimitations ? '▾' : '▸'} Scope &amp; Limitations
        </div>
        {showLimitations && (
          <div className="summary-limitations">
            <div className="summary-limitation">IS 800 implementation is a screening subset, not complete code compliance.</div>
            <div className="summary-limitation">Connection functionality is screening of declared connections, not connection design or FEA.</div>
            <div className="summary-limitation">Buckling implementation is Euler screening, not a buckling analysis.</div>
            <div className="summary-limitation">Experimental comparison is calibrated / reference-compared — independent validation is not claimed.</div>
            <div className="summary-limitation">Unsupported engineering inputs are marked NOT MODELED rather than assumed.</div>
            <div className="summary-limitation">Full soil mechanics is not implemented.</div>
            <div className="summary-limitation">Full time-history dynamic analysis is not implemented.</div>
            {evidence?.assumptions.filter((a) => !a.modeled).map((a, i) => (
              <div key={i} className="summary-limitation">
                <strong>{a.topic}:</strong> {a.description}
                {a.implication ? ` — ${a.implication}` : ''}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="view-section">
        <div className="section-heading-row">
          <div>
            <div className="section-title">Demonstrate &amp; Audit</div>
            <div className="section-helper">
              Failure Lab: remove member → analyze → structural response → autopsy →
              repair → re-analyze → before / after.
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-primary btn-sm" onClick={() => setActiveNavView('failure-lab')}>
            ▸ Run Failure Experiment
          </button>
          <button className="btn btn-sm" onClick={() => setActiveNavView('engineering-evidence')}>
            View Engineering Evidence
          </button>
          <button className="btn btn-sm" onClick={() => setActiveNavView('report')}>
            View Report
          </button>
        </div>
      </section>
    </div>
  );
}

function SummaryKV({ label, value, note, color }: {
  label: string; value: string; note?: string; color?: string;
}) {
  return (
    <div className="summary-kv">
      <div className="summary-kv-label">{label}</div>
      <div className="summary-kv-value" style={{ color }}>{value}</div>
      {note && <div className="summary-kv-note">{note}</div>}
    </div>
  );
}
