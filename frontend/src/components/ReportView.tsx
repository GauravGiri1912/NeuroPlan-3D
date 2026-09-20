/**
 * NeuroPlan-3D — Report
 *
 * A dedicated, discoverable home for the export action that already lives
 * in the global toolbar (server data only — spec, iterations, AI opinion,
 * evidence, verdict). No new export format or computation is introduced
 * here; this only explains what the toolbar's Export button produces.
 */
import { useAppStore } from '../stores/appStore';
import { exportReportJSON } from '../utils/exportReport';

export default function ReportView() {
  const spec = useAppStore((s) => s.spec);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const verificationStatus = useAppStore((s) => s.verificationStatus);
  const summary = useAppStore((s) => s.summary);
  const aiOpinion = useAppStore((s) => s.aiOpinion);
  const evidence = useAppStore((s) => s.evidence);
  const iterations = useAppStore((s) => s.iterations);

  const canExport = pipelineStage === 'complete' && spec !== null;

  return (
    <div className="view-content">
      <div className="view-header">
        <div className="text-label">Evidence</div>
        <h1 className="view-title">Report</h1>
        <div className="view-subtitle">
          Download the current analysis as a self-contained JSON report:
          the parsed specification, every solver iteration, the AI's
          unverified opinion, and the final verdict — a tangible,
          shareable artifact of what was actually computed.
        </div>
      </div>

      {!canExport && (
        <div className="empty-state" style={{ height: '40vh' }}>
          <div className="empty-state-icon">◇</div>
          <div className="empty-state-text">
            Run an analysis to completion before exporting a report.
          </div>
        </div>
      )}

      {canExport && spec && (
        <section className="view-section">
          <div className="section-title">Report Contents</div>
          <div style={{ fontSize: 12, color: '#b8bdc7', lineHeight: 1.8 }}>
            <div>• Parsed specification, including which values were assumed</div>
            <div>• Every solver iteration (structure + full FEA results)</div>
            <div>• The AI's unverified opinion, kept separate from the solver verdict</div>
            <div>• Result provenance, verification checks, and benchmark comparisons</div>
            <div>• Verdict: <strong style={{ color: verificationStatus === 'pass' ? '#22c55e' : '#ef4444' }}>
              {verificationStatus.toUpperCase()}
            </strong></div>
          </div>

          <button
            className="btn btn-primary"
            style={{ marginTop: 16 }}
            onClick={() => exportReportJSON({
              spec,
              verification_status: verificationStatus,
              summary,
              ai_opinion: aiOpinion,
              evidence,
              iterations,
            })}
          >
            ⬇ Export Report (JSON)
          </button>
        </section>
      )}
    </div>
  );
}
