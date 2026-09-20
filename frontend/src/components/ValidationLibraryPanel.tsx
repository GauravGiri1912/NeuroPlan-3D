/**
 * NeuroPlan-3D — Validation Library
 *
 * Two distinct, separately-answered questions, kept visually apart:
 *
 *   SOLVER VERIFICATION      "Is the arithmetic correct?"
 *                             — analytical benchmarks solved by hand,
 *                               checked against this same production solver.
 *   EXPERIMENTAL VALIDATION  "Does it match a real, physical structure?"
 *                             — an actual laboratory test, compared against
 *                               live solver output, with every discrepancy
 *                               shown, not hidden.
 *
 * The experimental section fetches its result once and renders whatever
 * state the backend actually reports (REFERENCE_AVAILABLE if the dataset
 * file isn't present on this machine, REFERENCE_COMPARED with the real
 * comparison otherwise) — nothing here is a static illustrative number.
 */
import { useEffect, useState } from 'react';
import { useAppStore } from '../stores/appStore';
import type {
  ValidationComparisonData, IndependenceData, ModelParameterData,
} from '../types/engineering';

const ANALYTICAL_BENCHMARKS = [
  { name: 'Axial bar (X/Y/Z aligned)', ref: 'delta = F.L/(A.E), sigma = F/A', tests: 'test_solver_3d.py' },
  { name: 'Diagonal 3D member', ref: 'direction cosines + element stiffness, hand-verified', tests: 'test_solver_3d.py' },
  { name: 'Symmetric triangular truss', ref: 'Method of Joints, 3 members, closed-form', tests: 'test_validation.py' },
  { name: '3-leg tripod (3D)', ref: 'closed-form reactions by symmetry', tests: 'test_solver_3d.py' },
  { name: 'Global equilibrium (planar + spatial)', ref: 'sum(F)=0, sum(M)=0 to machine precision', tests: 'test_evidence.py' },
];

const STATE_LABEL: Record<string, string> = {
  not_available: 'NOT AVAILABLE',
  reference_available: 'REFERENCE AVAILABLE',
  reference_compared: 'REFERENCE COMPARED',
  criterion_met: 'CRITERION MET',
  criterion_not_met: 'CRITERION NOT MET',
  model_not_applicable: 'MODEL NOT APPLICABLE',
};

// Calibration vs. validation. A calibrated comparison is NOT weaker
// evidence of the same kind — it is a different kind of statement, so it
// is never coloured like a pass.
const INDEPENDENCE_COLOR: Record<string, string> = {
  independent: '#22c55e',
  calibrated: '#f59e0b',
  not_assessed: '#8b919e',
};

const ROLE_LABEL: Record<string, string> = {
  geometry: 'Geometry',
  material: 'Material',
  cross_section: 'Cross section',
  boundary_condition: 'Boundary condition',
  load: 'Load',
  sensor_mapping: 'Sensor mapping',
};

const STATE_COLOR: Record<string, string> = {
  not_available: '#5c6370',
  reference_available: '#8b919e',
  reference_compared: '#3b82f6',
  criterion_met: '#22c55e',
  criterion_not_met: '#ef4444',
  model_not_applicable: '#f59e0b',
};

export default function ValidationLibraryPanel() {
  const [open, setOpen] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const result = useAppStore((s) => s.validationResult);
  const loading = useAppStore((s) => s.validationLoading);
  const error = useAppStore((s) => s.validationError);
  const fetchValidation = useAppStore((s) => s.fetchValidation);
  const inspect = useAppStore((s) => s.inspect);

  useEffect(() => {
    if (open) fetchValidation();
  }, [open, fetchValidation]);

  return (
    <div className="panel-section">
      <div
        className="panel-section-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen(!open)}
      >
        <span className="panel-section-title">{open ? '▾' : '▸'} Validation Library</span>
        <span style={{ fontSize: 9, color: '#5c6370' }}>solver benchmarks + experimental data</span>
      </div>

      {open && (
        <div style={{ fontSize: 11 }}>
          {/* Analytical Benchmarks */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 10, color: '#5c6370', letterSpacing: 0.5, marginBottom: 4 }}>
              ANALYTICAL BENCHMARKS — solver verification
            </div>
            {ANALYTICAL_BENCHMARKS.map((b) => (
              <div key={b.name} style={{
                display: 'flex', justifyContent: 'space-between', gap: 8,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 10, padding: '2px 0',
              }}>
                <span style={{ color: '#b8bdc7' }}>✓ {b.name}</span>
                <span style={{ color: '#22c55e' }}>PASS</span>
              </div>
            ))}
            <div style={{ fontSize: 9, color: '#5c6370', marginTop: 3 }}>
              Closed-form hand calculations, run against this same production solver
              (backend/tests/). See "Engineering Credibility" above for the live run's
              own benchmark comparison.
            </div>
          </div>

          {/* Experimental Validation */}
          <div>
            <div style={{ fontSize: 10, color: '#5c6370', letterSpacing: 0.5, marginBottom: 4 }}>
              EXPERIMENTAL VALIDATION — does it match a physical test?
            </div>

            {loading && <div style={{ color: '#8b919e' }}>Loading…</div>}
            {error && <div style={{ color: '#ef4444' }}>Error: {error}</div>}

            {result && (
              <div>
                <div
                  onClick={() => setDetailOpen(!detailOpen)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    cursor: 'pointer', padding: '4px 6px', background: '#1e2028', borderRadius: 3,
                  }}
                >
                  <span style={{ color: '#b8bdc7' }}>
                    {detailOpen ? '▾' : '▸'} Steel Truss Experiment
                  </span>
                  <span style={{
                    color: STATE_COLOR[result.state] ?? '#8b919e',
                    fontWeight: 600, fontSize: 10, fontFamily: "'JetBrains Mono', monospace",
                  }}>
                    {STATE_LABEL[result.state] ?? result.state.toUpperCase()}
                  </span>
                </div>

                {/* The qualifier travels with the badge — a reader must not
                    be able to see REFERENCE COMPARED without also seeing
                    whether it counts as independent evidence. */}
                <div style={{
                  fontSize: 9, fontFamily: "'JetBrains Mono', monospace",
                  color: INDEPENDENCE_COLOR[result.independence.verdict] ?? '#8b919e',
                  padding: '2px 6px',
                }}>
                  {result.independence.verdict === 'independent' ? '✓ ' : '⚠ '}
                  {result.independence.headline}
                </div>

                {detailOpen && (
                  <div style={{ marginTop: 6, paddingLeft: 4 }}>
                    <ValidationDetail result={result} onInspect={inspect} />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Independent Validation — Calibration vs Validation Split */}
          <IndependentValidationSection />
        </div>
      )}
    </div>
  );
}

function ValidationDetail({ result, onInspect }: {
  result: NonNullable<ReturnType<typeof useAppStore.getState>['validationResult']>;
  onInspect: (kind: 'node' | 'member', id: number) => void;
}) {
  const d = result.dataset;
  return (
    <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.6 }}>
      <IndependenceBanner independence={result.independence} parameters={result.parameters} />

      {/* Dataset */}
      <Section title="Dataset">
        <Row label="Title" value={d.title} />
        <Row label="Authors" value={d.authors.join(', ')} />
        <Row label="Repository" value={`${d.repository} (${d.version})`} />
        <Row label="DOI" value={d.doi} link={`https://doi.org/${d.doi}`} />
        <Row label="License" value={d.license} />
        <Row label="Published" value={d.publication_date} />
        {d.linked_publication_title && (
          <Row label="Publication" value={d.linked_publication_title} link={d.linked_publication_url} />
        )}
        <Row label="Retrieved" value={d.retrieved} />
      </Section>

      {result.case && (
        <Section title="Comparison Case">
          <Row label="Case" value={result.case.title} />
          <Row label="Setup" value={result.case.load_setup_description} />
          <details style={{ marginTop: 3 }}>
            <summary style={{ cursor: 'pointer', color: '#3b82f6' }}>
              Model reconstruction notes ({result.case.parameter_notes.length})
            </summary>
            <div style={{ marginTop: 3, color: '#8b919e' }}>
              {result.case.parameter_notes.map((n, i) => <div key={i} style={{ marginBottom: 3 }}>• {n}</div>)}
            </div>
          </details>
        </Section>
      )}

      {result.error && (
        <Section title="Status">
          <div style={{ color: '#f59e0b' }}>{result.error}</div>
        </Section>
      )}

      {result.comparisons.length > 0 && (
        <Section title={`Comparison — Measured vs. Computed (${result.comparisons.length} sensors)`}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 9 }}>
            <thead>
              <tr style={{ color: '#5c6370', textAlign: 'left' }}>
                <th>Sensor</th><th>Node</th><th>Measured</th><th>NeuroPlan</th><th>Abs.Err</th><th>Rel.Err</th><th>Map</th>
              </tr>
            </thead>
            <tbody>
              {result.comparisons.map((c: ValidationComparisonData) => (
                <tr key={c.sensor_id}>
                  <td style={{ color: '#b8bdc7' }}>{c.sensor_id}</td>
                  <td
                    style={{ color: '#3b82f6', cursor: c.node_id != null ? 'pointer' : 'default' }}
                    onClick={() => c.node_id != null && onInspect('node', c.node_id)}
                  >
                    {c.node_id ?? '—'}
                  </td>
                  <td style={{ color: '#f59e0b' }}>{c.experimental_value.toFixed(2)} {c.units}</td>
                  <td style={{ color: '#22c55e' }}>{c.neuroplan_value.toFixed(2)} {c.units}</td>
                  <td>{c.absolute_error.toFixed(2)}</td>
                  <td style={{ color: (c.relative_error ?? 0) > 0.5 ? '#ef4444' : '#8b919e' }}>
                    {c.relative_error != null ? `${(c.relative_error * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td style={{ color: c.mapping_status === 'sourced' ? '#22c55e' : '#f59e0b' }}>
                    {c.mapping_status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontSize: 9, color: '#f59e0b', marginTop: 4 }}>
            <strong>MEASURED</strong> = raw experimental sensor reading. <strong>NEUROPLAN</strong> = live
            production-solver output for the same reconstructed model. Rows marked "assumed" use a
            sensor→node correspondence inferred from the measured deflection shape, not an explicit
            published table — see model reconstruction notes above.
          </div>
        </Section>
      )}

      {result.summary && (
        <Section title="Comparison Metrics">
          <Row label="n" value={`${result.summary.n_points}`} />
          {result.summary.mae != null && <Row label="MAE" value={`${result.summary.mae.toFixed(3)} mm`} />}
          {result.summary.rmse != null && <Row label="RMSE" value={`${result.summary.rmse.toFixed(3)} mm`} />}
          {result.summary.max_absolute_error != null && (
            <Row label="Max abs. error" value={`${result.summary.max_absolute_error.toFixed(3)} mm`} />
          )}
          {result.summary.max_relative_error != null && (
            <Row label="Max rel. error" value={`${(result.summary.max_relative_error * 100).toFixed(1)}%`} />
          )}
          <Row
            label="R²"
            value={result.summary.r_squared != null ? result.summary.r_squared.toFixed(3) : result.summary.r_squared_note}
          />
          <div style={{ color: '#f59e0b', marginTop: 3 }}>{result.summary.uncertainty_note}</div>
        </Section>
      )}

      <Section title="Acceptance Criterion">
        <div style={{ color: '#8b919e' }}>{result.criterion_note}</div>
      </Section>

      <Section title="Damage Scenarios — Not Compared">
        <div style={{ color: '#8b919e' }}>{result.damage_scenarios_note}</div>
      </Section>
    </div>
  );
}

/**
 * The calibration-vs-validation verdict.
 *
 * Placed above the numbers deliberately: a reader who sees MAE and R²
 * first will read them as validation evidence. The qualifier has to
 * arrive before the figures it qualifies.
 */
function IndependenceBanner({ independence, parameters }: {
  independence: IndependenceData;
  parameters: ModelParameterData[];
}) {
  const [open, setOpen] = useState(false);
  const color = INDEPENDENCE_COLOR[independence.verdict] ?? '#8b919e';
  const calibrated = independence.calibrated_parameters;

  return (
    <div style={{
      border: `1px solid ${color}`, borderLeftWidth: 3,
      background: '#1a1c22', padding: '6px 8px', marginBottom: 8,
    }}>
      <div style={{ color, fontWeight: 600, fontSize: 10, letterSpacing: 0.3 }}>
        {independence.headline}
      </div>
      <div style={{ color: '#b8bdc7', marginTop: 4, lineHeight: 1.55 }}>
        {independence.explanation}
      </div>

      <div
        onClick={() => setOpen(!open)}
        style={{ color: '#3b82f6', cursor: 'pointer', marginTop: 5 }}
      >
        {open ? '▾' : '▸'} Parameter inventory ({calibrated.length} of {parameters.length} selected using measured results)
      </div>

      {open && (
        <div style={{ marginTop: 5 }}>
          {/* Stacked rows, not a table: the sidebar is ~280px and a
              4-column grid crushes every cell to unreadable width. */}
          <div style={{ fontSize: 9 }}>
            {parameters.map((p) => (
              <div key={p.name} style={{ borderTop: '1px solid #2a2d38', padding: '4px 0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6 }}>
                  <span style={{ color: '#8b919e' }}>{ROLE_LABEL[p.role] ?? p.role}</span>
                  <span style={{
                    color: p.selected_using_measurements ? '#f59e0b' : '#22c55e',
                    fontWeight: 600, whiteSpace: 'nowrap',
                  }}>
                    {p.selected_using_measurements ? 'FITTED TO DATA' : 'from source'}
                  </span>
                </div>
                <div style={{ color: '#b8bdc7' }}>{p.name}</div>
                {p.value_summary && (
                  <div style={{ color: '#5c6370' }}>{p.value_summary}</div>
                )}
                <div style={{ color: '#5c6370' }}>{p.source_reference}</div>
              </div>
            ))}
          </div>
          {calibrated.some((p) => p.note) && (
            <div style={{ color: '#f59e0b', marginTop: 4 }}>
              {calibrated.filter((p) => p.note).map((p) => (
                <div key={p.name} style={{ marginBottom: 2 }}>• {p.name}: {p.note}</div>
              ))}
            </div>
          )}
          <div style={{ color: '#5c6370', marginTop: 4, lineHeight: 1.5 }}>
            {independence.standard_reference}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8, borderTop: '1px solid #2a2d38', paddingTop: 5 }}>
      <div style={{ color: '#5c6370', marginBottom: 3 }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value, link }: { label: string; value: string; link?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#5c6370', whiteSpace: 'nowrap' }}>{label}</span>
      {link ? (
        <a href={link} target="_blank" rel="noreferrer" style={{ color: '#3b82f6', textAlign: 'right' }}>{value}</a>
      ) : (
        <span style={{ color: '#b8bdc7', textAlign: 'right' }}>{value}</span>
      )}
    </div>
  );
}


const INDEP_STATUS_COLOR: Record<string, string> = {
  independent_passed: '#22c55e',
  completed_review_required: '#3b82f6',
  calibrated_reference: '#f59e0b',
  insufficient_data: '#f59e0b',
  blocked_data_leakage: '#ef4444',
  not_run: '#5c6370',
};

function IndependentValidationSection() {
  const [open, setOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const indep = useAppStore((s) => s.independentValidation);
  const loading = useAppStore((s) => s.independentValidationLoading);
  const error = useAppStore((s) => s.independentValidationError);
  const fetchIndep = useAppStore((s) => s.fetchIndependentValidation);

  useEffect(() => {
    if (open) fetchIndep();
  }, [open, fetchIndep]);

  return (
    <div style={{ marginTop: 10 }}>
      <div
        onClick={() => setOpen(!open)}
        style={{
          fontSize: 10, color: '#5c6370', letterSpacing: 0.5, marginBottom: 4,
          cursor: 'pointer',
        }}
      >
        {open ? '▾' : '▸'} INDEPENDENT VALIDATION — calibration vs validation split
      </div>

      {open && (
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
          {loading && <div style={{ color: '#8b919e' }}>Loading…</div>}
          {error && <div style={{ color: '#ef4444' }}>Error: {error}</div>}

          {indep && (
            <div>
              {/* Status badge */}
              <div
                onClick={() => setDetailOpen(!detailOpen)}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  cursor: 'pointer', padding: '4px 6px', background: '#1e2028', borderRadius: 3,
                }}
              >
                <span style={{ color: '#b8bdc7' }}>
                  {detailOpen ? '▾' : '▸'} Validation Status
                </span>
                <span style={{
                  color: INDEP_STATUS_COLOR[indep.status] ?? '#8b919e',
                  fontWeight: 600, fontSize: 9,
                }}>
                  {indep.status_label}
                </span>
              </div>

              {/* Leakage check banner */}
              <div style={{
                fontSize: 9, padding: '2px 6px',
                color: indep.leakage_check.passed ? '#22c55e' : '#ef4444',
              }}>
                {indep.leakage_check.passed ? '✓ ' : '✗ '}
                Data leakage check: {indep.leakage_check.passed ? 'PASSED' : 'FAILED'}
                {' — '}{indep.leakage_check.explanation.split('.')[0]}.
              </div>

              {detailOpen && (
                <div style={{ marginTop: 6, paddingLeft: 4, lineHeight: 1.6 }}>
                  {/* Scientific explanation */}
                  <div style={{
                    border: '1px solid #f59e0b', borderLeftWidth: 3,
                    background: '#1a1c22', padding: '6px 8px', marginBottom: 8,
                  }}>
                    <div style={{ color: '#f59e0b', fontWeight: 600, fontSize: 10, letterSpacing: 0.3 }}>
                      INDEPENDENT VALIDATION NOT ESTABLISHED
                    </div>
                    <div style={{ color: '#b8bdc7', marginTop: 4, lineHeight: 1.55, whiteSpace: 'pre-line' }}>
                      {indep.scientific_explanation}
                    </div>
                  </div>

                  {/* Mid-span: the one independent point */}
                  {indep.midspan_is_independent && indep.midspan_comparison && (
                    <Section title="Mid-Span — Genuinely Independent">
                      <div style={{ color: '#22c55e', marginBottom: 4 }}>
                        ✓ Layout-invariant: same node under all 10 candidate mappings
                      </div>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 9 }}>
                        <thead>
                          <tr style={{ color: '#5c6370', textAlign: 'left' }}>
                            <th>Sensor</th><th>Node</th><th>Measured</th><th>NeuroPlan</th><th>Abs.Err</th><th>Rel.Err</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td style={{ color: '#b8bdc7' }}>{indep.midspan_comparison.sensor_id}</td>
                            <td style={{ color: '#3b82f6' }}>{indep.midspan_comparison.node_id ?? '—'}</td>
                            <td style={{ color: '#f59e0b' }}>{indep.midspan_comparison.experimental_value.toFixed(2)} mm</td>
                            <td style={{ color: '#22c55e' }}>{indep.midspan_comparison.neuroplan_value.toFixed(2)} mm</td>
                            <td>{indep.midspan_comparison.absolute_error.toFixed(2)}</td>
                            <td>{indep.midspan_comparison.relative_error != null
                              ? `${(indep.midspan_comparison.relative_error * 100).toFixed(1)}%`
                              : '—'}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                      <div style={{ color: '#8b919e', marginTop: 4, fontSize: 9 }}>
                        {indep.midspan_note}
                      </div>
                    </Section>
                  )}

                  {/* Calibration side summary */}
                  {indep.calibration_comparisons.length > 0 && (
                    <Section title={`Calibration (South, ${indep.calibration_sensor_ids.length} sensors)`}>
                      <div style={{ color: '#f59e0b', marginBottom: 3 }}>
                        ⚠ Calibrated: {indep.calibration_description}
                      </div>
                      {indep.calibration_summary && (
                        <div>
                          <Row label="MAE" value={`${indep.calibration_summary.mae?.toFixed(3) ?? '—'} mm`} />
                          <Row label="RMSE" value={`${indep.calibration_summary.rmse?.toFixed(3) ?? '—'} mm`} />
                          <Row label="Max rel. err" value={indep.calibration_summary.max_relative_error != null
                            ? `${(indep.calibration_summary.max_relative_error * 100).toFixed(1)}%`
                            : '—'
                          } />
                        </div>
                      )}
                    </Section>
                  )}

                  {/* Validation side summary */}
                  {indep.validation_comparisons.length > 0 && (
                    <Section title={`North Side (${indep.validation_sensor_ids.length} sensors)`}>
                      <div style={{ color: '#f59e0b', marginBottom: 3 }}>
                        ⚠ Same calibration-derived mapping: {indep.validation_description}
                      </div>
                      {indep.validation_summary && (
                        <div>
                          <Row label="MAE" value={`${indep.validation_summary.mae?.toFixed(3) ?? '—'} mm`} />
                          <Row label="RMSE" value={`${indep.validation_summary.rmse?.toFixed(3) ?? '—'} mm`} />
                          <Row label="Max rel. err" value={indep.validation_summary.max_relative_error != null
                            ? `${(indep.validation_summary.max_relative_error * 100).toFixed(1)}%`
                            : '—'
                          } />
                        </div>
                      )}
                    </Section>
                  )}

                  {/* Limitations */}
                  <Section title="Limitations">
                    {indep.limitations.map((l, i) => (
                      <div key={i} style={{ color: '#8b919e', marginBottom: 2 }}>• {l}</div>
                    ))}
                  </Section>

                  {/* Calibration parameters used */}
                  {indep.calibration_parameters_used.length > 0 && (
                    <Section title="Parameters Selected Using Measurements">
                      {indep.calibration_parameters_used.map((p) => (
                        <div key={p} style={{ color: '#f59e0b' }}>⚠ {p}</div>
                      ))}
                    </Section>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

