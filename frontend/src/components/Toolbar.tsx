/**
 * NeuroPlan-3D — Toolbar (Top Bar)
 *
 * Brand, current project/analysis identity, computation status, and the
 * two global actions (Export, Run Analysis). Deliberately does not carry
 * detailed engineering metrics — those live in the Overview/Results views.
 */
import { useAppStore } from '../stores/appStore';
import { exportReportJSON } from '../utils/exportReport';

const STRUCTURE_LABEL: Record<string, string> = {
  pratt: 'Pratt Truss',
  howe: 'Howe Truss',
  warren: 'Warren Truss',
  space_truss: 'Box Space Truss',
};

const STATUS_LABEL: Record<string, string> = {
  idle: 'No analysis run',
  parsing: 'Parsing…',
  parsed: 'Parsed',
  generating: 'Generating…',
  generated: 'Generated',
  analyzing: 'Analyzing…',
  analyzed: 'Analyzed',
  repairing: 'Repairing…',
  complete: 'Complete',
  error: 'Error',
};

const STATUS_COLOR: Record<string, string> = {
  idle: '#5c6370',
  complete: '#22c55e',
  error: '#ef4444',
};

export default function Toolbar() {
  const spec = useAppStore((s) => s.spec);
  const rawInput = useAppStore((s) => s.rawInput);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const verificationStatus = useAppStore((s) => s.verificationStatus);
  const summary = useAppStore((s) => s.summary);
  const aiOpinion = useAppStore((s) => s.aiOpinion);
  const evidence = useAppStore((s) => s.evidence);
  const iterations = useAppStore((s) => s.iterations);
  const runPipeline = useAppStore((s) => s.runPipeline);
  const runPipelineWithSpec = useAppStore((s) => s.runPipelineWithSpec);

  const isRunning = pipelineStage !== 'idle' && pipelineStage !== 'complete' && pipelineStage !== 'error';
  const canRun = !isRunning && (spec !== null || rawInput.trim() !== '');
  const canExport = pipelineStage === 'complete' && spec !== null;

  const handleRunAnalysis = () => {
    if (spec) runPipelineWithSpec(spec);
    else if (rawInput.trim()) runPipeline();
  };

  const statusColor = STATUS_COLOR[pipelineStage] ?? '#3b82f6';

  return (
    <div className="toolbar">
      <div className="toolbar-brand">
        <div className="toolbar-brand-icon">N</div>
        <span>NeuroPlan-3D</span>
      </div>
      <div className="toolbar-separator" />
      <span className="toolbar-project">
        {spec
          ? (spec.description?.trim() || STRUCTURE_LABEL[spec.structure_type] || spec.structure_type)
          : 'No project loaded'}
      </span>

      <div className="toolbar-spacer" />

      <span
        className="toolbar-status-pill"
        style={{ color: statusColor, borderColor: statusColor }}
      >
        <span className="toolbar-status-dot" style={{ background: statusColor }} />
        {STATUS_LABEL[pipelineStage] ?? pipelineStage}
      </span>

      <button
        className="btn btn-sm"
        disabled={!canExport}
        title="Download the full result (spec, every iteration, AI opinion, verdict) as JSON"
        onClick={() => spec && exportReportJSON({
          spec,
          verification_status: verificationStatus,
          summary,
          ai_opinion: aiOpinion,
          evidence,
          iterations,
        })}
      >
        Export
      </button>

      <button
        className="btn btn-primary btn-sm run-action-button"
        disabled={!canRun}
        onClick={handleRunAnalysis}
      >
        {isRunning ? (<><span className="spinner" /> Running…</>) : '▸ Run Analysis'}
      </button>
    </div>
  );
}
