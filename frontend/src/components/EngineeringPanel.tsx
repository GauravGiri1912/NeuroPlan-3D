/**
 * NeuroPlan-3D — Engineering Analysis panel
 *
 * Surfaces the hardening-pass results: what forces were applied and
 * under which named case, whether the system is numerically sound, and
 * what the screening checks found.
 *
 * Design rule carried over from the rest of the app: a capability that
 * is NOT implemented is shown saying so. The limitations are part of
 * the panel body, not hidden behind a tooltip — a reader has to be able
 * to see what the analysis does not cover without going looking for it.
 */
import { useEffect, useState } from 'react';
import { useAppStore } from '../stores/appStore';
import AnalysisModelBadge from './AnalysisModelBadge';
import type {
  LoadCaseSummaryData, MemberCodeReportData, BucklingScreeningData,
  ConnectionScreeningData, MemberData,
} from '../types/engineering';

const CASE_LABEL: Record<string, string> = {
  dead: 'Dead (self-weight)',
  live: 'Live (applied)',
  wind_plus_x: 'Wind +X',
  wind_minus_x: 'Wind -X',
  wind_plus_z: 'Wind +Z',
  wind_minus_z: 'Wind -Z',
  thermal: 'Thermal',
  settlement: 'Settlement',
};

const MONO = "'JetBrains Mono', monospace";

/** Backend MAX_VALID_TEMPERATURE_CHANGE_K — warn, don't block. */
const MAX_VALID_DT = 150;

export default function EngineeringPanel({ initialDetail = null }: { initialDetail?: string | null }) {
  const [open, setOpen] = useState(true);
  const [detail, setDetail] = useState<string | null>(initialDetail);
  const data = useAppStore((s) => s.engineering);
  const loading = useAppStore((s) => s.engineeringLoading);
  const error = useAppStore((s) => s.engineeringError);
  const selfWeight = useAppStore((s) => s.engineeringSelfWeight);
  const thermalRef = useAppStore((s) => s.engineeringThermalRef);
  const fetchEngineering = useAppStore((s) => s.fetchEngineering);
  const structure = useAppStore((s) => s.currentStructure());

  /** Local text state for the ΔT input — only committed on Apply.
   *  `prevThermalRef` tracks the last store value we synced from; when it
   *  changes (e.g. on reset) the local input is overwritten during render
   *  rather than via a setState-in-effect, satisfying the React Compiler. */
  const [dtInput, setDtInput] = useState(() => String(thermalRef));
  const [prevThermalRef, setPrevThermalRef] = useState(thermalRef);
  if (thermalRef !== prevThermalRef) {
    setPrevThermalRef(thermalRef);
    setDtInput(String(thermalRef));
  }
  /** Track whether local input has diverged from the last-applied value. */
  const dtParsed = Number(dtInput);
  const dtValid = dtInput.trim() !== '' && Number.isFinite(dtParsed);
  const dtPending = dtValid && dtParsed !== thermalRef;
  const dtActive = thermalRef !== 0;
  const dtOverLimit = dtValid && Math.abs(dtParsed) > MAX_VALID_DT;

  useEffect(() => {
    if (open) fetchEngineering();
  }, [open, fetchEngineering]);

  const toggle = (key: string) => setDetail(detail === key ? null : key);

  const applyThermal = () => {
    if (!dtValid) return;
    fetchEngineering(undefined, dtParsed);
  };

  return (
    <div className="panel-section engineering-panel">
      <div
        className="panel-section-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen(!open)}
      >
        <span className="panel-section-title">
          {open ? '▾' : '▸'} Engineering Analysis
        </span>
        <span style={{ fontSize: 9, color: '#5c6370' }}>loads · stability · screening</span>
      </div>

      {open && (
        <div style={{ fontSize: 11 }}>
          {loading && <div style={{ color: '#8b919e' }}>Analysing…</div>}
          {error && <div style={{ color: '#ef4444' }}>Error: {error}</div>}

          {data && (
            <div style={{ fontFamily: MONO, fontSize: 10, lineHeight: 1.6 }}>
              <AnalysisModelBadge model={data.model} />
              {/* Self-weight toggle — changing it re-runs the solver */}
              <div style={{
                display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginBottom: 6,
              }}>
                <span style={{ color: '#5c6370' }}>Self-weight</span>
                <button
                  onClick={() => fetchEngineering(!selfWeight)}
                  style={{
                    fontFamily: MONO, fontSize: 9, cursor: 'pointer',
                    background: selfWeight ? '#1f3a2b' : '#3a2b1f',
                    color: selfWeight ? '#22c55e' : '#f59e0b',
                    border: `1px solid ${selfWeight ? '#22c55e' : '#f59e0b'}`,
                    borderRadius: 3, padding: '2px 8px',
                  }}
                >
                  {selfWeight ? 'INCLUDED' : 'EXCLUDED'}
                </button>
              </div>

              {/* ── Thermal ΔT input ── */}
              <div style={{
                borderTop: '1px solid #2a2d38', paddingTop: 6, marginBottom: 6,
              }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4,
                }}>
                  <label
                    htmlFor="eng-thermal-dt"
                    style={{ color: '#5c6370', whiteSpace: 'nowrap' }}
                  >
                    Temperature ΔT
                  </label>
                  <input
                    id="eng-thermal-dt"
                    type="number"
                    step="any"
                    value={dtInput}
                    onChange={(e) => setDtInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') applyThermal(); }}
                    style={{
                      fontFamily: MONO, fontSize: 10, width: 72,
                      background: '#1a1d23', color: '#e1e4ea',
                      border: `1px solid ${!dtValid && dtInput.trim() !== '' ? '#ef4444' : '#2d3240'}`,
                      borderRadius: 3, padding: '2px 6px',
                      outline: 'none',
                    }}
                  />
                  <span style={{ color: '#5c6370', fontSize: 9 }}>K</span>
                  <button
                    onClick={applyThermal}
                    disabled={!dtPending}
                    style={{
                      fontFamily: MONO, fontSize: 9, cursor: dtPending ? 'pointer' : 'default',
                      background: dtPending ? '#1e3a5f' : '#22262e',
                      color: dtPending ? '#3b82f6' : '#5c6370',
                      border: `1px solid ${dtPending ? '#3b82f6' : '#2d3240'}`,
                      borderRadius: 3, padding: '2px 8px',
                      opacity: dtPending ? 1 : 0.5,
                    }}
                  >
                    Apply
                  </button>
                </div>

                {/* Status badge — clearly shows whether thermal load is active */}
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  alignItems: 'center',
                }}>
                  <span style={{
                    fontSize: 9,
                    color: dtActive ? '#22c55e' : '#5c6370',
                    fontWeight: dtActive ? 600 : 400,
                  }}>
                    {dtActive
                      ? `THERMAL LOAD APPLIED  ΔT = ${thermalRef > 0 ? '+' : ''}${thermalRef} K`
                      : 'NO THERMAL LOAD'}
                  </span>
                </div>

                {/* Validity warning when |ΔT| > 150 K */}
                {dtOverLimit && (
                  <div style={{ color: '#f59e0b', fontSize: 9, marginTop: 2 }}>
                    ⚠ |ΔT| {'>'} {MAX_VALID_DT} K — E held constant; NOT valid for fire.
                  </div>
                )}
              </div>

              <Row label="Max stress" value={`${data.max_stress_mpa.toFixed(2)} MPa`} />
              <Row label="Max displacement" value={`${data.max_displacement_mm.toFixed(3)} mm`} />
              <Row label="Total mass" value={`${data.total_weight_kg.toFixed(1)} kg`} />
              <Row
                label="Global equilibrium"
                value={data.equilibrium_passed ? 'PASS' : 'FAIL'}
                color={data.equilibrium_passed ? '#22c55e' : '#ef4444'}
              />

              {/* Load cases */}
              {data.load_summary && (
                <Block
                  title={`Load cases — ${data.load_summary.combination_name}`}
                  open={detail === 'loads'}
                  onToggle={() => toggle('loads')}
                >
                  {data.load_summary.cases.map((c) => (
                    <CaseRow key={c.case_type} c={c} />
                  ))}
                  <div style={{ color: '#5c6370', marginTop: 4 }}>
                    Total applied: {data.load_summary.total_applied_fy.toFixed(0)} N (Y)
                  </div>
                  {data.load_summary.self_weight?.included && (
                    <div style={{ color: '#5c6370' }}>
                      Self-weight {data.load_summary.self_weight.total_mass_kg.toFixed(1)} kg
                      × g = {data.load_summary.self_weight.total_weight_n.toFixed(0)} N,
                      applied at {data.load_summary.self_weight.n_loaded_nodes} nodes
                    </div>
                  )}
                  <div style={{ color: '#f59e0b', marginTop: 3 }}>
                    {data.load_summary.combination_source}
                  </div>
                </Block>
              )}

              {/* Stability */}
              {data.stability && (
                <Block
                  title={`Stability — ${data.stability.determinacy}`}
                  open={detail === 'stability'}
                  onToggle={() => toggle('stability')}
                >
                  <Row
                    label="Maxwell m+r vs 3n"
                    value={`${data.stability.n_members}+${data.stability.n_reaction_components} vs ${data.stability.required_dof}`}
                  />
                  <Row
                    label="Mechanism modes"
                    value={`${data.stability.n_zero_modes ?? '—'}`}
                    color={data.stability.n_zero_modes ? '#ef4444' : '#22c55e'}
                  />
                  <Row
                    label="Condition number"
                    value={data.stability.condition_number != null
                      ? data.stability.condition_number.toExponential(2) : '—'}
                  />
                  {data.stability.diagnostics.map((d, i) => (
                    <div key={i} style={{
                      marginTop: 4,
                      color: d.severity === 'error' ? '#ef4444' : '#f59e0b',
                    }}>
                      [{d.severity.toUpperCase()}] {d.title}
                      <div style={{ color: '#8b919e' }}>{d.explanation}</div>
                      {d.remedy && <div style={{ color: '#3b82f6' }}>Fix: {d.remedy}</div>}
                    </div>
                  ))}
                </Block>
              )}

              {/* Buckling */}
              <Block
                title={data.buckling.title}
                open={detail === 'buckling'}
                onToggle={() => toggle('buckling')}
              >
                <BucklingDetail buckling={data.buckling} />
              </Block>

              {/* IS 800 */}
              <Block
                title={data.code_checks.title}
                open={detail === 'code'}
                onToggle={() => toggle('code')}
              >
                <Row label="Code" value={`${data.code_checks.code}:${data.code_checks.edition}`} />
                <Row
                  label="Failed checks"
                  value={`${data.code_checks.n_failed}`}
                  color={data.code_checks.n_failed ? '#ef4444' : '#22c55e'}
                />
                <Row label="Max D/C ratio" value={data.code_checks.max_dc_ratio.toFixed(3)} />
                <div style={{ color: '#f59e0b', marginTop: 4 }}>
                  {data.code_checks.compliance_disclaimer}
                </div>
                <div style={{ color: '#5c6370', marginTop: 4 }}>IMPLEMENTED:</div>
                {data.code_checks.implemented_clauses.map((c, i) => (
                  <div key={i} style={{ color: '#22c55e' }}>✓ {c}</div>
                ))}
                <Limitations items={data.code_checks.unsupported_clauses} />
                <Is800MemberList members={data.code_checks.members} />
              </Block>

              {/* Connections */}
              <Block
                title={data.connections.title}
                open={detail === 'connections'}
                onToggle={() => toggle('connections')}
              >
                <ConnectionDetail connections={data.connections} members={structure?.members ?? []} />
              </Block>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CaseRow({ c }: { c: LoadCaseSummaryData }) {
  const label = CASE_LABEL[c.case_type] ?? c.case_type;
  const [state, color] = !c.supported
    ? ['NOT SUPPORTED', '#5c6370']
    : c.active
      ? [`ACTIVE ×${c.factor}`, '#22c55e']
      : ['idle', '#8b919e'];
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#b8bdc7', minWidth: 0 }}>{label}</span>
      <span style={{ color, whiteSpace: 'nowrap', flexShrink: 0 }}>{state}</span>
    </div>
  );
}

function Limitations({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ color: '#5c6370' }}>NOT MODELLED:</div>
      {items.map((item, i) => (
        <div key={i} style={{ color: '#8b919e' }}>• {item}</div>
      ))}
    </div>
  );
}

function Block({ title, open, onToggle, children }: {
  title: string; open: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
      <div onClick={onToggle} style={{ cursor: 'pointer', color: '#3b82f6' }}>
        {open ? '▾' : '▸'} {title}
      </div>
      {open && <div style={{ marginTop: 3 }}>{children}</div>}
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#5c6370', minWidth: 0 }}>{label}</span>
      <span style={{ color: color ?? '#b8bdc7', textAlign: 'right', flexShrink: 0 }}>{value}</span>
    </div>
  );
}

const BUCKLING_STATUS_COLOR: Record<string, string> = {
  pass: '#22c55e',
  fail: '#ef4444',
  unconservative: '#f59e0b',
  not_applicable: '#5c6370',
  not_modeled: '#8b919e',
};

const BUCKLING_STATUS_LABEL: Record<string, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  unconservative: 'REVIEW',
  not_applicable: 'N/A (tension)',
  not_modeled: 'NOT MODELED',
};

/**
 * BUCKLING SCREENING — deliberately never "full buckling analysis" or
 * "safe". Leads with the critical member (computed, never hardcoded —
 * see backend BucklingScreeningReport.governing_reason), then the
 * K-factor assumption (always shown, never implied universally correct),
 * then per-member evidence and the method's own stated limitations.
 */
function BucklingDetail({ buckling }: { buckling: BucklingScreeningData }) {
  const [showMembers, setShowMembers] = useState(false);
  const [showMethod, setShowMethod] = useState(false);
  const [expandedMember, setExpandedMember] = useState<number | null>(null);

  const governing = buckling.members.find((m) => m.member_id === buckling.governing_member_id) ?? null;

  return (
    <div>
      {governing ? (
        <>
          <Row label="Critical member" value={`M${governing.member_id}`} color="#3b82f6" />
          <div style={{ color: '#5c6370', marginBottom: 4, fontSize: 9 }}>{buckling.governing_reason}</div>
          <Row label="Slenderness KL/r" value={
            Number.isFinite(governing.slenderness) ? governing.slenderness.toFixed(1) : '—'
          } />
          <Row label="Euler critical load" value={
            Number.isFinite(governing.euler_critical_load)
              ? `${(governing.euler_critical_load / 1000).toFixed(1)} kN` : '—'
          } />
          <Row label="Compression demand" value={`${(Math.abs(governing.axial_force) / 1000).toFixed(1)} kN`} />
          <Row
            label="Status"
            value={BUCKLING_STATUS_LABEL[governing.status] ?? governing.status}
            color={BUCKLING_STATUS_COLOR[governing.status] ?? '#8b919e'}
          />
        </>
      ) : (
        <div style={{ color: '#5c6370' }}>No compression member identified.</div>
      )}

      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <Row label="Compression members" value={`${buckling.n_compression}`} />
        <Row
          label="Over Euler load"
          value={`${buckling.n_failed}`}
          color={buckling.n_failed ? '#ef4444' : '#22c55e'}
        />
        <Row
          label="Euler unconservative (REVIEW)"
          value={`${buckling.n_unconservative}`}
          color={buckling.n_unconservative ? '#f59e0b' : '#22c55e'}
        />
        <Row label="Max KL/r" value={buckling.max_slenderness.toFixed(1)} />
      </div>

      {/* Effective length factor K — always shown, never implied universal */}
      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <Row
          label="Effective length factor K"
          value={`${(governing?.k_factor ?? 1.0).toFixed(2)} — ASSUMED / CONFIGURED`}
          color="#f59e0b"
        />
      </div>

      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <div onClick={() => setShowMembers(!showMembers)} style={{ cursor: 'pointer', color: '#3b82f6' }}>
          {showMembers ? '▾' : '▸'} Member Details ({buckling.members.length} members)
        </div>
        {showMembers && (
          <div style={{ marginTop: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {buckling.members.map((m) => {
              const isExpanded = expandedMember === m.member_id;
              return (
                <div key={m.member_id}>
                  <div
                    onClick={() => setExpandedMember(isExpanded ? null : m.member_id)}
                    style={{
                      display: 'flex', justifyContent: 'space-between', gap: 8,
                      cursor: 'pointer', padding: '2px 0',
                    }}
                  >
                    <span style={{ color: '#b8bdc7' }}>
                      {isExpanded ? '▾' : '▸'} M{m.member_id}
                      <span style={{ color: '#5c6370' }}> · {m.is_compression ? 'compression' : 'tension'}</span>
                    </span>
                    <span style={{ color: BUCKLING_STATUS_COLOR[m.status] ?? '#8b919e', flexShrink: 0 }}>
                      {BUCKLING_STATUS_LABEL[m.status] ?? m.status}
                    </span>
                  </div>
                  {isExpanded && (
                    <div style={{
                      marginLeft: 8, paddingLeft: 6, borderLeft: '2px solid #2a2d38',
                      display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 4,
                    }}>
                      <Row label="Axial force" value={`${(m.axial_force / 1000).toFixed(2)} kN`} />
                      <Row label="Length" value={`${m.length.toFixed(3)} m`} />
                      <Row label="Area" value={`${(m.area * 1e4).toFixed(2)} cm²`} />
                      <Row label="I" value={`${(m.inertia * 1e8).toFixed(3)} cm⁴`} />
                      <Row label="E" value={`${(m.E / 1e9).toFixed(0)} GPa`} />
                      <Row label="Radius of gyration" value={`${(m.radius_of_gyration * 1000).toFixed(1)} mm`} />
                      <Row label="Effective length KL" value={`${m.effective_length.toFixed(3)} m`} />
                      <Row label="K" value={m.k_factor.toFixed(2)} />
                      <Row label="Slenderness KL/r" value={
                        Number.isFinite(m.slenderness) ? m.slenderness.toFixed(1) : '—'
                      } />
                      <Row label="Transition λc" value={
                        Number.isFinite(m.transition_slenderness) ? m.transition_slenderness.toFixed(1) : '—'
                      } />
                      <Row label="Column class" value={m.column_class.replace(/_/g, ' ')} />
                      <Row label="Euler critical load" value={
                        Number.isFinite(m.euler_critical_load) ? `${(m.euler_critical_load / 1000).toFixed(1)} kN` : '—'
                      } />
                      {m.is_compression && (
                        <Row label="Utilisation" value={
                          Number.isFinite(m.utilisation) ? m.utilisation.toFixed(3) : '—'
                        } />
                      )}
                      {m.note && <div style={{ color: '#f59e0b', marginTop: 2 }}>{m.note}</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <div onClick={() => setShowMethod(!showMethod)} style={{ cursor: 'pointer', color: '#3b82f6' }}>
          {showMethod ? '▾' : '▸'} Method / Assumptions
        </div>
        {showMethod && (
          <div style={{ marginTop: 3, color: '#8b919e', lineHeight: 1.5 }}>{buckling.k_basis}</div>
        )}
      </div>

      <div style={{ color: '#f59e0b', marginTop: 4 }}>{buckling.disclaimer}</div>
      <Limitations items={buckling.method_limitations} />
    </div>
  );
}

const CONNECTION_STATUS_COLOR: Record<string, string> = {
  pass: '#22c55e',
  fail: '#ef4444',
  not_modeled: '#8b919e',
};

const CONNECTION_STATUS_LABEL: Record<string, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  not_modeled: 'NOT MODELED',
};

const BOLT_GRADES = ['4.6', '4.8', '5.6', '8.8', '10.9'];
const BOLT_DIAMETERS = [12, 16, 20, 22, 24, 30];

/**
 * CONNECTION SCREENING — closed-form IS 800 Section 10 capacity equations
 * against the real member force, for connections the user explicitly
 * declares. Never "connection design" or "connection FEA": no gusset
 * plate, no prying, no eccentricity, no bolt-group geometry — see
 * unsupported_checks, always shown, never trimmed.
 *
 * Declaring a connection is deliberately a SINGLE controlled input (like
 * Failure Lab's one-controlled-repair convention) rather than a general
 * connection editor — this is a screening tool, not a design tool.
 */
function ConnectionDetail({ connections, members }: {
  connections: ConnectionScreeningData;
  members: MemberData[];
}) {
  const declared = useAppStore((s) => s.declaredConnection);
  const setDeclaredConnection = useAppStore((s) => s.setDeclaredConnection);
  const fetchEngineering = useAppStore((s) => s.fetchEngineering);
  const loading = useAppStore((s) => s.engineeringLoading);

  const [formType, setFormType] = useState<'bolted' | 'welded'>('bolted');
  const [formMemberId, setFormMemberId] = useState<number | null>(null);
  const [boltDiameter, setBoltDiameter] = useState(20);
  const [boltGrade, setBoltGrade] = useState('8.8');
  const [boltCount, setBoltCount] = useState(1);
  const [weldSize, setWeldSize] = useState(6);
  const [weldLength, setWeldLength] = useState(200);
  const [shopWeld, setShopWeld] = useState(true);

  const [showSummaries, setShowSummaries] = useState(false);
  const [showMethod, setShowMethod] = useState(false);
  const [expandedMember, setExpandedMember] = useState<number | null>(null);

  const governing = connections.summaries.find(
    (s) => s.member_id === connections.governing_member_id,
  ) ?? null;

  const declareAndRun = () => {
    if (formMemberId === null) return;
    setDeclaredConnection(
      formType === 'bolted'
        ? { kind: 'bolted', member_id: formMemberId, bolt_diameter_mm: boltDiameter,
            bolt_grade: boltGrade, bolt_count: boltCount }
        : { kind: 'welded', member_id: formMemberId, weld_size_mm: weldSize,
            weld_length_mm: weldLength, shop_weld: shopWeld },
    );
    fetchEngineering();
  };

  const clearDeclaration = () => {
    setDeclaredConnection(null);
    fetchEngineering();
  };

  return (
    <div>
      {/* Prominent summary — governing check first, never buried in the list */}
      {governing ? (
        <>
          <Row label="Connection / member" value={`M${governing.member_id}`} color="#3b82f6" />
          <Row label="Governing check" value={governing.governing_check_name} />
          <Row label="Demand" value={`${(governing.demand / 1000).toFixed(2)} kN`} />
          <Row label="Capacity" value={`${(governing.capacity / 1000).toFixed(2)} kN`} />
          <Row label="Utilization" value={governing.dc_ratio.toFixed(3)} />
          <Row
            label="Status"
            value={CONNECTION_STATUS_LABEL[governing.status] ?? governing.status}
            color={CONNECTION_STATUS_COLOR[governing.status] ?? '#8b919e'}
          />
        </>
      ) : (
        <div style={{ color: '#5c6370', marginBottom: 4 }}>
          No connection declared yet — declare one below to see a real screening result.
        </div>
      )}

      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <Row
          label="Members NOT MODELED"
          value={`${connections.members_without_connection.length}`}
          color="#f59e0b"
        />
        <Row
          label="Failed checks"
          value={`${connections.n_failed}`}
          color={connections.n_failed ? '#ef4444' : '#22c55e'}
        />
      </div>

      {/* Declare Connection — single controlled input */}
      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <div style={{ color: '#5c6370', marginBottom: 4 }}>Declare Connection</div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
          <select
            value={formMemberId ?? ''}
            onChange={(e) => setFormMemberId(e.target.value === '' ? null : Number(e.target.value))}
            style={selectStyleSm}
          >
            <option value="">Select member…</option>
            {members.map((m) => <option key={m.id} value={m.id}>M{m.id}</option>)}
          </select>
          <select value={formType} onChange={(e) => setFormType(e.target.value as 'bolted' | 'welded')} style={selectStyleSm}>
            <option value="bolted">Bolted</option>
            <option value="welded">Welded</option>
          </select>
        </div>

        {formType === 'bolted' ? (
          <div style={{ display: 'flex', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
            <label style={{ color: '#8b919e', fontSize: 9 }}>
              M<select value={boltDiameter} onChange={(e) => setBoltDiameter(Number(e.target.value))} style={selectStyleSm}>
                {BOLT_DIAMETERS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <label style={{ color: '#8b919e', fontSize: 9 }}>
              Grade <select value={boltGrade} onChange={(e) => setBoltGrade(e.target.value)} style={selectStyleSm}>
                {BOLT_GRADES.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
            <label style={{ color: '#8b919e', fontSize: 9 }}>
              Count <input type="number" min={1} value={boltCount}
                onChange={(e) => setBoltCount(Math.max(1, Number(e.target.value)))}
                style={{ width: 40, fontFamily: MONO, fontSize: 9 }} />
            </label>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
            <label style={{ color: '#8b919e', fontSize: 9 }}>
              Size (mm) <input type="number" min={1} value={weldSize}
                onChange={(e) => setWeldSize(Number(e.target.value))}
                style={{ width: 40, fontFamily: MONO, fontSize: 9 }} />
            </label>
            <label style={{ color: '#8b919e', fontSize: 9 }}>
              Length (mm) <input type="number" min={1} value={weldLength}
                onChange={(e) => setWeldLength(Number(e.target.value))}
                style={{ width: 55, fontFamily: MONO, fontSize: 9 }} />
            </label>
            <label style={{ color: '#8b919e', fontSize: 9 }}>
              <input type="checkbox" checked={shopWeld} onChange={(e) => setShopWeld(e.target.checked)} /> Shop weld
            </label>
          </div>
        )}

        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={declareAndRun}
            disabled={loading || formMemberId === null}
            style={{
              fontFamily: MONO, fontSize: 10, cursor: loading ? 'default' : 'pointer',
              background: '#1e2028', color: '#3b82f6', border: '1px solid #3b82f6',
              borderRadius: 3, padding: '3px 10px', opacity: formMemberId === null ? 0.5 : 1,
            }}
          >
            {loading ? 'Screening…' : 'Screen Connection'}
          </button>
          {declared && (
            <button
              onClick={clearDeclaration}
              disabled={loading}
              style={{
                fontFamily: MONO, fontSize: 10, cursor: 'pointer',
                background: '#1e2028', color: '#8b919e', border: '1px solid #2a2d38',
                borderRadius: 3, padding: '3px 10px',
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Bolt/Weld Details — per member */}
      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <div onClick={() => setShowSummaries(!showSummaries)} style={{ cursor: 'pointer', color: '#3b82f6' }}>
          {showSummaries ? '▾' : '▸'} Bolt / Weld Details ({connections.summaries.length} members)
        </div>
        {showSummaries && (
          <div style={{ marginTop: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {connections.summaries.map((s) => {
              const isExpanded = expandedMember === s.member_id;
              const memberChecks = connections.checks.filter((c) => c.member_id === s.member_id);
              return (
                <div key={s.member_id}>
                  <div
                    onClick={() => setExpandedMember(isExpanded ? null : s.member_id)}
                    style={{
                      display: 'flex', justifyContent: 'space-between', gap: 8,
                      cursor: 'pointer', padding: '2px 0',
                    }}
                  >
                    <span style={{ color: '#b8bdc7' }}>
                      {isExpanded ? '▾' : '▸'} M{s.member_id}
                      <span style={{ color: '#5c6370' }}> · {s.connection_type.replace(/_/g, ' ')}</span>
                    </span>
                    <span style={{ color: CONNECTION_STATUS_COLOR[s.status] ?? '#8b919e', flexShrink: 0 }}>
                      {CONNECTION_STATUS_LABEL[s.status] ?? s.status}
                    </span>
                  </div>
                  {isExpanded && (
                    <div style={{
                      marginLeft: 8, paddingLeft: 6, borderLeft: '2px solid #2a2d38',
                      display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 4,
                    }}>
                      {memberChecks.map((c, i) => (
                        <div key={i}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span style={{ color: '#3b82f6' }}>{c.check_name}</span>
                            <span style={{ color: CONNECTION_STATUS_COLOR[c.status] ?? '#8b919e', flexShrink: 0 }}>
                              {CONNECTION_STATUS_LABEL[c.status] ?? c.status}
                            </span>
                          </div>
                          <div style={{ color: '#5c6370' }}>{c.clause}</div>
                          <div style={{ color: '#8b919e', marginTop: 1 }}>{c.equation}</div>
                          {Object.entries(c.inputs).map(([k, v]) => (
                            <Row key={k} label={`  ${k}`} value={v} />
                          ))}
                          {c.status !== 'not_modeled' && (
                            <Row label="  D/C ratio" value={c.dc_ratio.toFixed(3)}
                                 color={CONNECTION_STATUS_COLOR[c.status]} />
                          )}
                          {c.note && <div style={{ color: '#f59e0b', marginTop: 2 }}>{c.note}</div>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
        <div onClick={() => setShowMethod(!showMethod)} style={{ cursor: 'pointer', color: '#3b82f6' }}>
          {showMethod ? '▾' : '▸'} Method / Assumptions
        </div>
        {showMethod && (
          <div style={{ marginTop: 3, color: '#8b919e', lineHeight: 1.5 }}>
            Closed-form IS 800:2007 Section 10 capacity equations (bolt shear cl.
            10.4.3, bolt bearing cl. 10.3.4, fillet weld cl. 10.5.7.1), evaluated
            against the real member force from the solver. Not a connection
            finite-element model.
          </div>
        )}
      </div>

      <div style={{ color: '#f59e0b', marginTop: 4 }}>{connections.disclaimer}</div>
      <Limitations items={connections.unsupported_checks} />
    </div>
  );
}

const selectStyleSm: React.CSSProperties = {
  fontFamily: MONO, fontSize: 9, background: '#1e2028', color: '#b8bdc7',
  border: '1px solid #2a2d38', borderRadius: 3,
};

const IS800_STATUS_COLOR: Record<string, string> = {
  pass: '#22c55e',
  fail: '#ef4444',
  not_applicable: '#5c6370',
  not_supported: '#f59e0b',
};

const IS800_STATUS_LABEL: Record<string, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  not_applicable: 'N/A',
  not_supported: 'NOT SUPPORTED',
};

/**
 * All members, every IS 800 check evaluated for each — the same data the
 * backend already computes, previously only summarised as an aggregate
 * count. Shown for every member (not just a "worst N") since a screening
 * that hides which members it actually checked is not more trustworthy
 * for being shorter.
 */
function Is800MemberList({ members }: { members: MemberCodeReportData[] }) {
  const [open, setOpen] = useState(false);
  const [expandedMember, setExpandedMember] = useState<number | null>(null);

  if (members.length === 0) return null;

  return (
    <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
      <div onClick={() => setOpen(!open)} style={{ cursor: 'pointer', color: '#3b82f6' }}>
        {open ? '▾' : '▸'} Per-member results ({members.length} members)
      </div>
      {open && (
        <div style={{ marginTop: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {members.map((m) => {
            const passFail = m.checks.filter((c) => c.status === 'pass' || c.status === 'fail');
            const worst = passFail.some((c) => c.status === 'fail') ? 'fail' : 'pass';
            const worstDc = passFail.reduce((max, c) => Math.max(max, c.dc_ratio), 0);
            const isExpanded = expandedMember === m.member_id;
            return (
              <div key={m.member_id}>
                <div
                  onClick={() => setExpandedMember(isExpanded ? null : m.member_id)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', gap: 8,
                    cursor: 'pointer', padding: '2px 0',
                  }}
                >
                  <span style={{ color: '#b8bdc7' }}>
                    {isExpanded ? '▾' : '▸'} M{m.member_id}
                    <span style={{ color: '#5c6370' }}> · {m.section_class} · {m.is_compression ? 'C' : 'T'}</span>
                  </span>
                  <span style={{ color: IS800_STATUS_COLOR[worst], flexShrink: 0 }}>
                    {IS800_STATUS_LABEL[worst]} · D/C {worstDc.toFixed(3)}
                  </span>
                </div>
                {isExpanded && (
                  <div style={{
                    marginLeft: 8, paddingLeft: 6, borderLeft: '2px solid #2a2d38',
                    display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 4,
                  }}>
                    <Row label="Axial force" value={`${(m.axial_force / 1000).toFixed(2)} kN`} />
                    {m.checks.map((c, i) => (
                      <div key={i} style={{ marginTop: 2 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span style={{ color: '#3b82f6' }}>{c.check_name}</span>
                          <span style={{ color: IS800_STATUS_COLOR[c.status], flexShrink: 0 }}>
                            {IS800_STATUS_LABEL[c.status]}
                          </span>
                        </div>
                        <div style={{ color: '#5c6370' }}>{c.clause}</div>
                        <div style={{ color: '#8b919e', marginTop: 1 }}>{c.equation}</div>
                        {Object.entries(c.inputs).map(([k, v]) => (
                          <Row key={k} label={`  ${k}`} value={v} />
                        ))}
                        {c.status !== 'not_supported' && (
                          <Row label="  D/C ratio" value={c.dc_ratio.toFixed(3)}
                               color={IS800_STATUS_COLOR[c.status]} />
                        )}
                        {c.note && (
                          <div style={{ color: '#f59e0b', marginTop: 2 }}>{c.note}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
