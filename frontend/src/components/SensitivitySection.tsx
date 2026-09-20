/**
 * NeuroPlan-3D — Sensitivity Analysis
 *
 * Consumes the existing POST /api/engineering/sensitivity endpoint
 * (server.core.analysis.sensitivity.run_sensitivity) — a one-at-a-time
 * deterministic perturbation study already implemented and tested on the
 * backend. This is new frontend UI for it; no sensitivity math is done
 * here, and every number, label, and disclaimer shown is copied verbatim
 * from the response.
 */
import { useState } from 'react';
import { useAppStore } from '../stores/appStore';
import AnalysisModelBadge from './AnalysisModelBadge';
import type { AnalysisModelMeta } from '../types/engineering';

const API_BASE = '/api';
const MONO = "'JetBrains Mono', monospace";

interface OutputSensitivity {
  output_name: string;
  baseline: number;
  minimum: number;
  maximum: number;
  change_percent: number;
  normalised_slope: number;
}

interface ParameterSensitivity {
  parameter: string;
  label: string;
  baseline_value: number;
  perturbation: number;
  low_value: number;
  high_value: number;
  outputs: Record<string, OutputSensitivity>;
  failed: boolean;
  failure_reason: string;
}

interface SensitivityReport {
  model?: AnalysisModelMeta;
  baseline: Record<string, number>;
  perturbation: number;
  parameters: ParameterSensitivity[];
  dominant: Record<string, string>;
  method: string;
  is_statistical: boolean;
  statistical_disclaimer: string;
  interaction_limitation: string;
}

async function post(path: string, body: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail ? String(data.detail) : `HTTP ${res.status}`);
  return data as SensitivityReport;
}

export default function SensitivitySection() {
  const spec = useAppStore((s) => s.spec);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<SensitivityReport | null>(null);

  const run = async () => {
    setLoading(true); setError(null);
    try {
      setReport(await post('/engineering/sensitivity', { spec }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setReport(null);
    }
    setLoading(false);
  };

  return (
    <div className="view-content">
      <div className="view-header">
        <div className="text-label">Engineering</div>
        <h1 className="view-title">Sensitivity</h1>
        <div className="view-subtitle">
          One-at-a-time deterministic perturbation: each input parameter is
          scaled up and down and the full production solver is re-run — not
          a statistical or probabilistic analysis.
        </div>
      </div>

      <button
        className="btn btn-primary btn-sm run-action-button"
        onClick={run}
        disabled={loading || !spec}
        title={!spec ? 'Load or run an analysis first — no current model to analyze.' : undefined}
        style={{ marginBottom: 8 }}
      >
        {loading ? 'Running…' : '▸ Run Sensitivity Sweep'}
      </button>

      {!spec && (
        <div style={{ fontSize: 11, color: '#f59e0b', marginBottom: 16 }}>
          No current model — load or run an analysis first.
        </div>
      )}

      {error && <div style={{ color: '#ef4444', marginBottom: 12, fontSize: 12 }}>{error}</div>}

      {report && (
        <>
          <AnalysisModelBadge model={report.model} />
          <section className="view-section">
            <div className="section-title">Method</div>
            <div style={{ fontSize: 12, color: '#b8bdc7', lineHeight: 1.6 }}>{report.method}</div>
            <div style={{
              marginTop: 8, padding: '8px 10px', background: '#3d2a0f',
              border: '1px solid #6b4a15', borderRadius: 3, fontSize: 11, color: '#fbbf24',
            }}>
              {report.statistical_disclaimer}
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: '#8b919e' }}>
              {report.interaction_limitation}
            </div>
          </section>

          <section className="view-section">
            <div className="section-title">Parameter Sensitivity — Max Displacement / Max Stress</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th className="num">Baseline</th>
                  <th className="num">Range (±{(report.perturbation * 100).toFixed(0)}%)</th>
                  <th className="num">Δ Displacement</th>
                  <th className="num">Δ Stress</th>
                </tr>
              </thead>
              <tbody>
                {report.parameters.map((p) => {
                  const dispOut = p.outputs['max_displacement_mm'];
                  const stressOut = p.outputs['max_stress_mpa'];
                  return (
                    <tr key={p.parameter} className={p.failed ? 'status-warning' : undefined}>
                      <td>{p.label}</td>
                      <td className="num" style={{ fontFamily: MONO }}>{p.baseline_value.toPrecision(4)}</td>
                      <td className="num" style={{ fontFamily: MONO }}>
                        {p.low_value.toPrecision(4)} – {p.high_value.toPrecision(4)}
                      </td>
                      <td className="num" style={{ fontFamily: MONO }}>
                        {p.failed ? '—' : dispOut ? `${dispOut.change_percent.toFixed(1)}%` : '—'}
                      </td>
                      <td className="num" style={{ fontFamily: MONO }}>
                        {p.failed ? '—' : stressOut ? `${stressOut.change_percent.toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {report.parameters.some((p) => p.failed) && (
              <div style={{ fontSize: 10, color: '#f59e0b', marginTop: 6 }}>
                Rows in amber failed to solve at that perturbation — see the
                backend's failure_reason for that parameter.
              </div>
            )}
          </section>

          <section className="view-section">
            <div className="section-title">Dominant Parameter per Output</div>
            {Object.entries(report.dominant).map(([output, param]) => (
              <div key={output} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
                <span style={{ color: '#5c6370' }}>{output}</span>
                <span style={{ color: '#e1e4ea' }}>{param}</span>
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
