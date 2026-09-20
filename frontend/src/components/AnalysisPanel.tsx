/**
 * NeuroPlan-3D — Analysis Panel (Right Panel)
 *
 * Contains:
 * - Verification badge (PASS/FAIL)
 * - Key metrics grid
 * - Member results table
 * - Failure list
 * - Repair timeline
 * - Iteration selector
 */
import { useAppStore } from '../stores/appStore';
import { stressRatioToHex, statusColor } from '../utils/colorScales';
import AIVsPhysicsCard from './AIVsPhysicsCard';

export default function AnalysisPanel() {
  const iterations = useAppStore((s) => s.iterations);
  const currentIndex = useAppStore((s) => s.currentIterationIndex);
  const verificationStatus = useAppStore((s) => s.verificationStatus);
  const summary = useAppStore((s) => s.summary);
  const aiOpinion = useAppStore((s) => s.aiOpinion);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const setCurrentIteration = useAppStore((s) => s.setCurrentIteration);
  const selectedMemberId = useAppStore((s) => s.selectedMemberId);
  const setSelectedMember = useAppStore((s) => s.setSelectedMember);

  if (iterations.length === 0) {
    return (
      <div className="view-content">
        <div className="empty-state" style={{ height: '70vh' }}>
          <div className="empty-state-icon">◇</div>
          <div className="empty-state-text" style={{ maxWidth: 320 }}>
            <strong>AI proposes. Physics decides.</strong>
            <br /><br />
            The AI only reads your description and guesses parameters — it never
            calculates anything. Every stress, displacement, and pass/fail verdict
            you'll see here comes from a real Direct Stiffness Method solver, run
            after the AI's proposal, with no AI influence on the result.
            <br /><br />
            Run a demo preset or enter a requirement to see the two compared,
            side by side.
          </div>
        </div>
      </div>
    );
  }

  const currentIter = iterations[currentIndex];
  const results = currentIter?.results;
  const diagnosis = results?.diagnosis;

  return (
    <div className="view-content">
      <div className="view-header">
        <div className="text-label">Analysis</div>
        <h1 className="view-title">Results</h1>
        <div className="view-subtitle">Linear Static · Direct Stiffness</div>
      </div>

      {/* AI vs. Physics comparison — the core claim, made checkable.
          Compares the AI's opinion against the INITIAL (pre-repair) physics
          result, since that's the apples-to-apples "AI's proposal vs. reality"
          moment — not whatever iteration the user is currently scrubbed to. */}
      <AIVsPhysicsCard
        aiOpinion={aiOpinion}
        physicsPassed={iterations[0]?.results.diagnosis.passed ?? false}
        pipelineStage={pipelineStage}
        wasRepaired={iterations.length > 1}
      />

      {/* Verification Badge — scoped to the computation, never to real-world safety */}
      <div className="panel-section">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <div
            className={`verification-badge ${verificationStatus}`}
            style={{ flex: 1 }}
            title="All configured numerical and structural checks passed for this computational model. This is not a real-world safety certification."
          >
            {verificationStatus === 'pass' ? '✓' : verificationStatus === 'fail' ? '✗' : '◌'}
            {' '}
            {verificationStatus === 'pass'
              ? 'COMPUTATION VERIFIED'
              : verificationStatus === 'fail'
                ? `${diagnosis?.failed_member_count || 0} FAILURES FOUND`
                : 'PENDING ANALYSIS'}
          </div>
        </div>

        {pipelineStage === 'complete' && (
          <div style={{ marginTop: 6, fontSize: 10, lineHeight: 1.5 }}>
            <div style={{ color: '#8b919e' }}>
              All configured numerical and structural checks passed for this
              <strong> computational model</strong>.
            </div>
            <div style={{
              marginTop: 4,
              display: 'flex',
              justifyContent: 'space-between',
              color: '#f59e0b',
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              <span>REAL-WORLD VALIDATION</span>
              <span style={{ fontWeight: 600 }}>NOT PERFORMED</span>
            </div>
          </div>
        )}
      </div>

      {/* Computational verification breakdown — every check shown separately,
          so "verified" is never a single opaque badge. */}
      {results?.checks && (
        <div className="panel-section">
          <div className="panel-section-header">
            <span className="panel-section-title">Computational Checks</span>
            <span style={{
              fontSize: 10,
              color: results.checks.all_passed ? '#22c55e' : '#ef4444',
            }}>
              {results.is_spatial ? '3D SPATIAL' : '2D PLANAR'} · {results.dof_count} DOF
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <CheckRow label="Solver" ok={results.checks.solver} />
            <CheckRow label="Geometry" ok={results.checks.geometry} />
            <CheckRow label="Boundary Conditions" ok={results.checks.boundary_conditions} />
            <CheckRow
              label="Force Equilibrium"
              ok={results.equilibrium.relative_residual <= results.equilibrium.tolerance}
              detail={`ΣF residual ${results.equilibrium.relative_residual.toExponential(1)}`}
            />
            <CheckRow
              label="Moment Equilibrium"
              ok={results.equilibrium.relative_moment_residual <= results.equilibrium.tolerance}
              detail={`ΣM residual ${results.equilibrium.relative_moment_residual.toExponential(1)}`}
            />
            <CheckRow
              label="Stress"
              ok={results.checks.stress}
              detail={`σ ratio ${diagnosis?.max_stress_ratio.toFixed(3)}`}
            />
            <CheckRow
              label="Displacement"
              ok={results.checks.displacement}
              detail={`${diagnosis?.max_displacement_mm.toFixed(1)} mm`}
            />
          </div>
          <div style={{ fontSize: 9, color: '#5c6370', marginTop: 6, lineHeight: 1.4 }}>
            Computational verification only — not professional engineering
            certification.
          </div>
        </div>
      )}

      {/* Key Metrics */}
      {results && (
        <div className="panel-section">
          <div className="panel-section-header">
            <span className="panel-section-title">Key Metrics</span>
          </div>
          <div className="metric-grid">
            <MetricCard
              label="Max Stress Ratio"
              value={diagnosis?.max_stress_ratio.toFixed(3) || '—'}
              status={diagnosis && diagnosis.max_stress_ratio > 1 ? 'danger' : 'ok'}
            />
            <MetricCard
              label="Max Displacement"
              value={`${diagnosis?.max_displacement_mm.toFixed(2) || '—'}`}
              unit="mm"
            />
            <MetricCard
              label="Total Weight"
              value={results.total_weight_kg.toFixed(1)}
              unit="kg"
            />
            <MetricCard
              label="Solve Time"
              value={results.solve_time_ms.toFixed(1)}
              unit="ms"
            />
            <MetricCard
              label="Members"
              value={`${results.member_results.length}`}
            />
            <MetricCard
              label="Iterations"
              value={`${iterations.length}`}
            />
          </div>
        </div>
      )}

      {/* Iteration Selector */}
      {iterations.length > 1 && (
        <div className="panel-section">
          <div className="panel-section-header">
            <span className="panel-section-title">Iteration</span>
            <span className="text-value" style={{ fontSize: 10, color: '#8b919e' }}>
              {currentIndex} / {iterations.length - 1}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={iterations.length - 1}
            value={currentIndex}
            onChange={(e) => setCurrentIteration(parseInt(e.target.value))}
            style={{ width: '100%', accentColor: '#3b82f6' }}
          />
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: 10,
            color: '#5c6370',
            marginTop: 2,
          }}>
            <span>Initial</span>
            <span>Final</span>
          </div>
        </div>
      )}

      {/* Before/After Comparison */}
      {iterations.length > 1 && summary && (
        <div className="panel-section">
          <div className="panel-section-header">
            <span className="panel-section-title">Before / After</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <ComparisonRow
              label="Failures"
              before={`${summary.initial_failures ?? '—'}`}
              after={`${summary.final_failures ?? '—'}`}
              improved={(summary.final_failures ?? 0) < (summary.initial_failures ?? 0)}
            />
            <ComparisonRow
              label="Max σ Ratio"
              before={`${(summary.initial_max_stress_ratio ?? 0).toFixed(3)}`}
              after={`${(summary.final_max_stress_ratio ?? 0).toFixed(3)}`}
              improved={(summary.final_max_stress_ratio ?? 0) < (summary.initial_max_stress_ratio ?? 0)}
            />
            <ComparisonRow
              label="Weight"
              before={`${(summary.initial_weight_kg ?? 0).toFixed(1)} kg`}
              after={`${(summary.final_weight_kg ?? 0).toFixed(1)} kg`}
            />
          </div>
        </div>
      )}

      {/* Failure List */}
      {diagnosis && diagnosis.failures.length > 0 && currentIndex === iterations.length - 1 && (
        <div className="panel-section">
          <div className="panel-section-header">
            <span className="panel-section-title">Failures</span>
            <span style={{ fontSize: 10, color: '#ef4444' }}>
              {diagnosis.failures.length}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {diagnosis.failures.slice(0, 10).map((f, i) => (
              <div
                key={i}
                style={{
                  fontSize: 10,
                  padding: '4px 6px',
                  background: '#3d1515',
                  borderLeft: '3px solid #ef4444',
                  borderRadius: 2,
                  color: '#e1e4ea',
                  fontFamily: "'JetBrains Mono', monospace",
                  cursor: f.member_id != null ? 'pointer' : 'default',
                }}
                onClick={() => f.member_id != null && setSelectedMember(f.member_id)}
              >
                {f.description}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Member Table */}
      {results && (
        <div className="panel-section" style={{ padding: 0 }}>
          <div className="panel-section-header" style={{ padding: '10px 12px 6px' }}>
            <span className="panel-section-title">Member Results</span>
          </div>
          <div style={{ maxHeight: 300, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th className="num">Force (kN)</th>
                  <th className="num">σ (MPa)</th>
                  <th className="num">Ratio</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {results.member_results.map((mr) => {
                  const isSelected = selectedMemberId === mr.member_id;
                  return (
                    <tr
                      key={mr.member_id}
                      className={
                        mr.status === 'ok' ? 'status-ok'
                          : mr.status === 'overstressed' ? 'status-fail'
                            : 'status-warning'
                      }
                      style={{
                        cursor: 'pointer',
                        background: isSelected ? '#1e3a5f' : undefined,
                      }}
                      onClick={() => setSelectedMember(
                        isSelected ? null : mr.member_id
                      )}
                    >
                      <td>{mr.member_id}</td>
                      <td className="num">{mr.axial_force_kn.toFixed(1)}</td>
                      <td className="num">{mr.stress_mpa.toFixed(1)}</td>
                      <td
                        className="num"
                        style={{ color: stressRatioToHex(mr.stress_ratio) }}
                      >
                        {mr.stress_ratio.toFixed(3)}
                      </td>
                      <td>
                        <span style={{
                          display: 'inline-block',
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: statusColor(mr.status),
                        }} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Repair Timeline */}
      {iterations.length > 1 && (
        <div className="panel-section">
          <div className="panel-section-header">
            <span className="panel-section-title">Repair History</span>
          </div>
          <div className="repair-timeline">
            {iterations.map((it, i) => (
              <div
                key={i}
                className="timeline-item"
                style={{
                  cursor: 'pointer',
                  background: currentIndex === i ? '#1e3a5f' : undefined,
                }}
                onClick={() => setCurrentIteration(i)}
              >
                <div className="timeline-marker">
                  <div className={`timeline-dot ${it.results.diagnosis.passed ? 'pass' : 'fail'}`} />
                  {i < iterations.length - 1 && <div className="timeline-line" />}
                </div>
                <div className="timeline-content">
                  <div className="timeline-title">
                    {i === 0 ? 'Initial Analysis' : `Iteration ${i}`}
                  </div>
                  <div className="timeline-detail">
                    {it.repair_action
                      ? `${it.repair_action.strategy.replace(/_/g, ' ')} — ${it.repair_action.rationale}`
                      : `${it.results.diagnosis.failed_member_count} failures, σ_max ratio ${it.results.diagnosis.max_stress_ratio.toFixed(3)}`
                    }
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Verification Check Row ───

function CheckRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      fontSize: 11,
      fontFamily: "'JetBrains Mono', monospace",
      padding: '2px 0',
    }}>
      <span style={{ color: '#8b919e' }}>{label}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {detail && <span style={{ fontSize: 9, color: '#5c6370' }}>{detail}</span>}
        <span style={{ color: ok ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
          {ok ? 'PASS' : 'FAIL'}
        </span>
      </span>
    </div>
  );
}

// ─── Metric Card ───

function MetricCard({ label, value, unit, status }: {
  label: string;
  value: string;
  unit?: string;
  status?: 'ok' | 'danger';
}) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{
        color: status === 'danger' ? '#ef4444' : undefined,
      }}>
        {value}
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
    </div>
  );
}

// ─── Comparison Row ───

function ComparisonRow({ label, before, after, improved }: {
  label: string;
  before: string;
  after: string;
  improved?: boolean;
}) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      fontSize: 11,
      padding: '2px 0',
    }}>
      <span className="field-label" style={{ fontSize: 10, flex: '0 0 80px' }}>{label}</span>
      <span className="text-value" style={{ fontSize: 11, color: '#8b919e' }}>{before}</span>
      <span style={{ color: '#5c6370', margin: '0 4px' }}>→</span>
      <span className="text-value" style={{
        fontSize: 11,
        color: improved ? '#22c55e' : '#e1e4ea',
      }}>
        {after}
      </span>
    </div>
  );
}
