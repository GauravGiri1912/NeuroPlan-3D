/**
 * NeuroPlan-3D — Status Bar (Bottom)
 *
 * Pipeline progress indicator and status information.
 */
import { useAppStore } from '../stores/appStore';

const STAGES = [
  { key: 'parsing', label: 'Parse' },
  { key: 'generating', label: 'Generate' },
  { key: 'analyzing', label: 'Analyze' },
  { key: 'repairing', label: 'Repair' },
  { key: 'complete', label: 'Verify' },
];

const STAGE_ORDER = ['idle', 'parsing', 'parsed', 'generating', 'generated', 'analyzing', 'analyzed', 'repairing', 'complete'];

export default function StatusBar() {
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const pipelineMessage = useAppStore((s) => s.pipelineMessage);
  const error = useAppStore((s) => s.error);
  const iterations = useAppStore((s) => s.iterations);
  const currentResults = useAppStore((s) => s.currentResults());

  const currentOrder = STAGE_ORDER.indexOf(pipelineStage);

  return (
    <div className="statusbar">
      {/* Pipeline stages */}
      <div className="pipeline-stages">
        {STAGES.map((stage, i) => {
          const stageOrder = STAGE_ORDER.indexOf(stage.key);
          let status = 'pending';
          if (pipelineStage === 'error') {
            status = currentOrder > stageOrder ? 'complete' : 'pending';
          } else if (currentOrder >= stageOrder && pipelineStage !== 'idle') {
            status = currentOrder === stageOrder ? 'active' : 'complete';
          } else if (pipelineStage === 'complete') {
            status = 'complete';
          }

          return (
            <div key={stage.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {i > 0 && <div className="stage-separator" />}
              <div className={`pipeline-stage ${status}`}>
                <div className="stage-dot" />
                <span>{stage.label}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ flex: 1 }} />

      {/* Status message */}
      {error ? (
        <span style={{ color: '#ef4444', fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}>
          Error: {error}
        </span>
      ) : pipelineMessage ? (
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}>
          {pipelineMessage}
        </span>
      ) : null}

      {/* Solve time */}
      {currentResults && (
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#5c6370' }}>
          Solve: {currentResults.solve_time_ms.toFixed(1)} ms
        </span>
      )}

      {/* Iteration count */}
      {iterations.length > 0 && (
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#5c6370' }}>
          Iterations: {iterations.length}
        </span>
      )}
    </div>
  );
}
