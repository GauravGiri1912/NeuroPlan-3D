/**
 * NeuroPlan-3D — Advanced Analysis panel
 *
 * Surfaces capabilities added after the initial engineering pass:
 * geometric/material nonlinearity (P-Delta), modal + IS 1893 seismic
 * response spectrum, fatigue screening, fire (elevated-temperature
 * strength reduction), elastic spring supports, and the deterministic
 * load robustness sweep.
 *
 * Each sub-section fetches on demand (its own "Run" action) rather than
 * eagerly, since several require additional inputs (spring stiffness,
 * seismic zone/soil, fatigue detail-category strength) that have no
 * safe default. Every result carries its own scope/limitation text
 * verbatim from the backend — never summarised away.
 */
import { useState } from 'react';
import { useAppStore } from '../stores/appStore';
import AnalysisModelBadge from './AnalysisModelBadge';

const API_BASE = '/api';
const MONO = "'JetBrains Mono', monospace";

async function post(path: string, body: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail ? String(data.detail) : `HTTP ${res.status}`);
  }
  return data;
}

export default function AdvancedAnalysisPanel({ initialSection = null }: { initialSection?: string | null }) {
  const [open, setOpen] = useState(true);
  const [section, setSection] = useState<string | null>(initialSection);

  return (
    <div className="panel-section">
      <div
        className="panel-section-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen(!open)}
      >
        <span className="panel-section-title">
          {open ? '▾' : '▸'} Advanced Analysis
        </span>
        <span style={{ fontSize: 9, color: '#5c6370' }}>
          nonlinear · seismic · fatigue · fire · springs
        </span>
      </div>

      {open && (
        <div style={{ fontSize: 11, fontFamily: MONO }}>
          <Block title="Nonlinear (P-Delta / material)" id="nonlinear" section={section} setSection={setSection}>
            <NonlinearSection />
          </Block>
          <Block title="Modal Analysis" id="modal" section={section} setSection={setSection}>
            <ModalSection />
          </Block>
          <Block title="Seismic — IS 1893 Response Spectrum" id="seismic" section={section} setSection={setSection}>
            <SeismicSection />
          </Block>
          <Block title="Fatigue Screening" id="fatigue" section={section} setSection={setSection}>
            <FatigueSection />
          </Block>
          <Block title="Fire — Elevated Temperature" id="fire" section={section} setSection={setSection}>
            <FireSection />
          </Block>
          <Block title="Elastic Spring Supports" id="springs" section={section} setSection={setSection}>
            <SpringsSection />
          </Block>
          <Block title="Deterministic Load Robustness" id="robustness" section={section} setSection={setSection}>
            <RobustnessSection />
          </Block>
        </div>
      )}
    </div>
  );
}

function Block({ title, id, section, setSection, children }: {
  title: string; id: string; section: string | null;
  setSection: (v: string | null) => void; children: React.ReactNode;
}) {
  const open = section === id;
  return (
    <div style={{ borderTop: '1px solid #2a2d38', marginTop: 6, paddingTop: 4 }}>
      <div onClick={() => setSection(open ? null : id)} style={{ cursor: 'pointer', color: '#3b82f6' }}>
        {open ? '▾' : '▸'} {title}
      </div>
      {open && <div style={{ marginTop: 4, paddingLeft: 2 }}>{children}</div>}
    </div>
  );
}

function RunButton({ onClick, loading, label = 'Run', disabled = false, disabledReason }: {
  onClick: () => void; loading: boolean; label?: string;
  disabled?: boolean; disabledReason?: string;
}) {
  const isDisabled = loading || disabled;
  return (
    <>
      <button
        className="run-action-button"
        onClick={onClick}
        disabled={isDisabled}
        title={disabled ? disabledReason : undefined}
        style={{
          fontFamily: MONO, fontSize: 10, cursor: isDisabled ? 'default' : 'pointer',
          background: '#1e2028', color: '#3b82f6', border: '1px solid #3b82f6',
          borderRadius: 3, padding: '3px 10px', marginBottom: disabled ? 2 : 6,
          opacity: disabled ? 0.5 : 1,
        }}
      >
        {loading ? 'Running…' : label}
      </button>
      {disabled && disabledReason && (
        <div style={{ color: '#f59e0b', fontSize: 9, marginBottom: 6 }}>{disabledReason}</div>
      )}
    </>
  );
}

function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return <div style={{ color: '#ef4444', marginBottom: 6 }}>{error}</div>;
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#5c6370', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ color: color ?? '#b8bdc7', textAlign: 'right' }}>{value}</span>
    </div>
  );
}

function ScopeNote({ text }: { text?: string }) {
  if (!text) return null;
  return <div style={{ color: '#f59e0b', marginTop: 4, fontSize: 9 }}>{text}</div>;
}

// ───────────────────────── Nonlinear ─────────────────────────

function NonlinearSection() {
  const spec = useAppStore((s) => s.spec);
  const [geometric, setGeometric] = useState(true);
  const [material, setMaterial] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/nonlinear', { spec, geometric, material, n_steps: 20, max_iterations: 60 });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 6 }}>
        <label style={{ color: '#8b919e' }}>
          <input type="checkbox" checked={geometric} onChange={(e) => setGeometric(e.target.checked)} /> Geometric (P-Delta)
        </label>
        <label style={{ color: '#8b919e' }}>
          <input type="checkbox" checked={material} onChange={(e) => setMaterial(e.target.checked)} /> Material (elastic-plastic)
        </label>
      </div>
      <RunButton onClick={run} loading={loading} disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />
      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <Row label="Converged" value={result.converged ? 'YES' : 'NO'} color={result.converged ? '#22c55e' : '#ef4444'} />
          {!result.converged && <Row label="Reason" value={result.divergence_reason ?? '—'} color="#ef4444" />}
          {result.converged && (
            <>
              <Row label="Load steps completed" value={String(result.steps?.length ?? 0)} />
              <Row label="Any member yielded" value={result.any_yielded ? 'YES' : 'no'} />
            </>
          )}
          <ScopeNote text={result.scope_note} />
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Modal ─────────────────────────

function ModalSection() {
  const spec = useAppStore((s) => s.spec);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/modal', { spec, n_modes: 6 });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); }
    setLoading(false);
  };

  return (
    <div>
      <RunButton onClick={run} loading={loading} disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />
      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <Row label="Total mass" value={`${result.total_mass_kg.toFixed(1)} kg`} />
          <Row label="Mass participation X/Y" value={
            `${result.mass_participation_x_percent.toFixed(1)}% / ${result.mass_participation_y_percent.toFixed(1)}%`
          } />
          <table style={{ width: '100%', marginTop: 4, fontSize: 9 }}>
            <thead>
              <tr style={{ color: '#5c6370', textAlign: 'left' }}>
                <th>Mode</th><th>f (Hz)</th><th>T (s)</th><th>Eff. mass X%</th><th>Eff. mass Y%</th>
              </tr>
            </thead>
            <tbody>
              {result.modes.map((m: any) => (
                <tr key={m.mode_number}>
                  <td style={{ color: '#b8bdc7' }}>{m.mode_number}</td>
                  <td>{m.frequency_hz.toFixed(2)}</td>
                  <td>{m.period_s.toFixed(4)}</td>
                  <td>{(100 * m.effective_mass_x / result.total_mass_kg).toFixed(1)}</td>
                  <td>{(100 * m.effective_mass_y / result.total_mass_kg).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ScopeNote text={result.mass_model_note} />
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Seismic ─────────────────────────

const ZONES = ['ii', 'iii', 'iv', 'v'];
const SOILS = ['type_i_rock_hard', 'type_ii_medium', 'type_iii_soft'];

function SeismicSection() {
  const spec = useAppStore((s) => s.spec);
  const [zone, setZone] = useState('iv');
  const [soil, setSoil] = useState('type_ii_medium');
  const [importanceFactor, setImportanceFactor] = useState(1.0);
  const [responseReduction, setResponseReduction] = useState(3.0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/seismic', {
        spec, zone, soil, importance_factor: importanceFactor,
        response_reduction_factor: responseReduction, direction: 'x',
      });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
        <select value={zone} onChange={(e) => setZone(e.target.value)} style={selectStyle}>
          {ZONES.map((z) => <option key={z} value={z}>Zone {z.toUpperCase()}</option>)}
        </select>
        <select value={soil} onChange={(e) => setSoil(e.target.value)} style={selectStyle}>
          {SOILS.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
        <label style={{ color: '#8b919e', fontSize: 9 }}>
          I: <input type="number" step="0.1" value={importanceFactor}
                    onChange={(e) => setImportanceFactor(Number(e.target.value))}
                    style={{ width: 40, fontFamily: MONO }} />
        </label>
        <label style={{ color: '#8b919e', fontSize: 9 }}>
          R: <input type="number" step="0.1" value={responseReduction}
                    onChange={(e) => setResponseReduction(Number(e.target.value))}
                    style={{ width: 40, fontFamily: MONO }} />
        </label>
      </div>
      <RunButton onClick={run} loading={loading} disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />
      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <Row label="Base shear (SRSS)" value={`${result.base_shear_srss_n.toFixed(1)} N`} />
          <Row label="Combination" value={result.combination_method} />
          {result.mode_contributions.map((c: any) => (
            <Row key={c.mode_number} label={`  mode ${c.mode_number} (T=${c.period_s.toFixed(3)}s)`}
                value={`Sa/g=${c.sa_over_g.toFixed(3)} Vb=${c.base_shear_n.toFixed(0)}N`} />
          ))}
          <ScopeNote text={result.combination_caveat} />
          <ScopeNote text={result.scope_note} />
        </div>
      )}
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  fontFamily: MONO, fontSize: 9, background: '#1e2028', color: '#b8bdc7',
  border: '1px solid #2a2d38', borderRadius: 3,
};

// ───────────────────────── Fatigue ─────────────────────────

function FatigueSection() {
  const spec = useAppStore((s) => s.spec);
  const [sigmaC, setSigmaC] = useState(100);
  const [designCycles, setDesignCycles] = useState(2_000_000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/fatigue', {
        spec, detail_category_name: 'User-supplied', sigma_c_mpa: sigmaC,
        m: 3.0, n_ref: 2_000_000, design_cycles: designCycles,
      });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
        <label style={{ color: '#8b919e', fontSize: 9 }}>
          sigma_c (MPa, IS 800 Table 26): <input type="number" value={sigmaC}
            onChange={(e) => setSigmaC(Number(e.target.value))} style={{ width: 50, fontFamily: MONO }} />
        </label>
        <label style={{ color: '#8b919e', fontSize: 9 }}>
          Design cycles: <input type="number" value={designCycles}
            onChange={(e) => setDesignCycles(Number(e.target.value))} style={{ width: 90, fontFamily: MONO }} />
        </label>
      </div>
      <RunButton onClick={run} loading={loading} disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />
      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <Row label="Failed checks" value={String(result.n_failed)} color={result.n_failed ? '#ef4444' : '#22c55e'} />
          <Row label="Governing member" value={String(result.governing_member_id ?? '—')} />
          <Row label="Max usage ratio" value={result.max_usage_ratio.toFixed(4)} />
          <ScopeNote text={result.disclaimer} />
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Fire ─────────────────────────

function FireSection() {
  const spec = useAppStore((s) => s.spec);
  const [temperature, setTemperature] = useState(600);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/fire', { spec, temperature_c: temperature });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); }
    setLoading(false);
  };

  return (
    <div>
      <label style={{ color: '#8b919e', fontSize: 9, display: 'block', marginBottom: 6 }}>
        Temperature (°C): <input type="number" value={temperature} min={20} max={1200}
          onChange={(e) => setTemperature(Number(e.target.value))} style={{ width: 60, fontFamily: MONO }} />
      </label>
      <RunButton onClick={run} loading={loading} disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />
      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <Row label="Failed members" value={String(result.n_failed)} color={result.n_failed ? '#ef4444' : '#22c55e'} />
          <Row label="Max utilisation" value={result.max_utilisation.toFixed(3)} />
          {Object.entries(result.properties_by_material ?? {}).map(([key, props]: [string, any]) => (
            <Row key={key} label={`  ${key} k_y/k_E`} value={`${props.k_y_theta.toFixed(3)} / ${props.k_e_theta.toFixed(3)}`} />
          ))}
          <ScopeNote text={result.source_citation} />
          <ScopeNote text={result.disclaimer} />
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Springs ─────────────────────────

function SpringsSection() {
  const spec = useAppStore((s) => s.spec);
  const [nodeId, setNodeId] = useState(0);
  const [ky, setKy] = useState(1e8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/springs', {
        spec, springs: [{ node_id: nodeId, kx: 0, ky, kz: 0 }],
      });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
        <label style={{ color: '#8b919e', fontSize: 9 }}>
          Node: <input type="number" value={nodeId}
            onChange={(e) => setNodeId(Number(e.target.value))} style={{ width: 40, fontFamily: MONO }} />
        </label>
        <label style={{ color: '#8b919e', fontSize: 9 }}>
          k_y (N/m): <input type="number" value={ky}
            onChange={(e) => setKy(Number(e.target.value))} style={{ width: 90, fontFamily: MONO }} />
        </label>
      </div>
      <RunButton onClick={run} loading={loading} disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />
      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <Row label="Baseline max disp" value={`${result.baseline.max_displacement_mm.toFixed(3)} mm`} />
          <Row label="With spring max disp" value={`${result.with_springs.max_displacement_mm.toFixed(3)} mm`} />
          <Row label="Baseline max stress" value={`${result.baseline.max_stress_mpa.toFixed(2)} MPa`} />
          <Row label="With spring max stress" value={`${result.with_springs.max_stress_mpa.toFixed(2)} MPa`} />
          <ScopeNote text={result.source_note} />
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Deterministic Load Robustness ─────────────────────────

interface RobustnessScenario {
  load_scale: number;
  structural_status: 'stable' | 'solved_but_failed_checks' | 'unstable';
  max_displacement_mm: number | null;
  max_stress_mpa: number | null;
  critical_member: number | null;
  verified: boolean | null;
  error: string | null;
}

interface RobustnessSummary {
  total_scenarios: number;
  stable_scenarios: number;
  unstable_scenarios: number;
  failed_check_scenarios: number;
  max_observed_displacement_mm: number | null;
  max_observed_stress_mpa: number | null;
}

interface RobustnessSweepResult {
  model?: import('../types/engineering').AnalysisModelMeta;
  load_index: number;
  scales: number[];
  scenarios: RobustnessScenario[];
  summary: RobustnessSummary;
  terminology_note: string;
}

const ROBUSTNESS_STATUS_LABEL: Record<string, string> = {
  stable: 'PASS',
  solved_but_failed_checks: 'FAIL',
  unstable: 'UNSTABLE',
};

const ROBUSTNESS_STATUS_COLOR: Record<string, string> = {
  stable: '#22c55e',
  solved_but_failed_checks: '#ef4444',
  unstable: '#ef4444',
};

function RobustnessSection() {
  const spec = useAppStore((s) => s.spec);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RobustnessSweepResult | null>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      const data = await post('/engineering/experiments/load-robustness', { spec });
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unknown error'); setResult(null); }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ color: '#8b919e', fontSize: 9, marginBottom: 6 }}>
        Results are evaluated at fixed load scales using the deterministic
        structural solver. This is not a probabilistic reliability analysis.
      </div>
      <RunButton onClick={run} loading={loading} label="Run Load Sweep" disabled={!spec} disabledReason="No current model — load or run an analysis first." />
      <ErrorText error={error} />

      {result && (
        <div>
          <AnalysisModelBadge model={result.model} />
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 9, marginBottom: 6 }}>
            <thead>
              <tr style={{ color: '#5c6370', textAlign: 'left' }}>
                <th>Load</th><th>Status</th><th>Max Disp.</th><th>Max Stress</th><th>Crit. Member</th>
              </tr>
            </thead>
            <tbody>
              {result.scenarios.map((s) => (
                <tr key={s.load_scale} style={{ borderTop: '1px solid #2a2d38' }}>
                  <td style={{ color: '#b8bdc7' }}>{s.load_scale.toFixed(2)}×</td>
                  <td style={{
                    color: ROBUSTNESS_STATUS_COLOR[s.structural_status] ?? '#8b919e',
                    fontWeight: 600,
                  }}>
                    {ROBUSTNESS_STATUS_LABEL[s.structural_status] ?? s.structural_status}
                  </td>
                  <td style={{ color: '#b8bdc7' }}>
                    {s.max_displacement_mm !== null ? `${s.max_displacement_mm.toFixed(3)} mm` : '—'}
                  </td>
                  <td style={{ color: '#b8bdc7' }}>
                    {s.max_stress_mpa !== null ? `${s.max_stress_mpa.toFixed(2)} MPa` : '—'}
                  </td>
                  <td style={{ color: '#b8bdc7' }}>
                    {s.critical_member !== null ? `M${s.critical_member}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.scenarios.some((s) => s.structural_status === 'unstable') && (
            <div style={{ color: '#ef4444', fontSize: 9, marginBottom: 6 }}>
              One or more scenarios could not be solved. Load scaling alone
              cannot change whether the structure is a mechanism — an
              unstable result here reflects the baseline model itself, not
              increased load. See the scenario error text below.
              {result.scenarios.filter((s) => s.error).map((s, i) => (
                <div key={i} style={{ color: '#8b919e', whiteSpace: 'pre-wrap', marginTop: 4 }}>
                  {s.load_scale.toFixed(2)}×: {s.error}
                </div>
              ))}
            </div>
          )}

          <Row label="Total scenarios" value={String(result.summary.total_scenarios)} />
          <Row label="Stable" value={String(result.summary.stable_scenarios)} color="#22c55e" />
          <Row label="Solved, failed checks" value={String(result.summary.failed_check_scenarios)}
               color={result.summary.failed_check_scenarios ? '#ef4444' : undefined} />
          <Row label="Unstable" value={String(result.summary.unstable_scenarios)}
               color={result.summary.unstable_scenarios ? '#ef4444' : undefined} />
          <Row label="Max observed displacement" value={
            result.summary.max_observed_displacement_mm !== null
              ? `${result.summary.max_observed_displacement_mm.toFixed(3)} mm` : '—'
          } />
          <Row label="Max observed stress" value={
            result.summary.max_observed_stress_mpa !== null
              ? `${result.summary.max_observed_stress_mpa.toFixed(2)} MPa` : '—'
          } />
          <ScopeNote text={result.terminology_note} />
        </div>
      )}
    </div>
  );
}
