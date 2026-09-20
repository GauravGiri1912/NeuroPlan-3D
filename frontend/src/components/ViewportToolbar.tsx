/**
 * NeuroPlan-3D — Viewport Toolbar
 *
 * Overlay controls for the 3D viewport:
 * - Display mode toggles (Wireframe, Stress, Displacement, Failure)
 * - Label toggle
 * - Load/support visibility
 * - Deformed shape toggle
 */
import { useAppStore } from '../stores/appStore';
import type { DisplayMode } from '../types/engineering';

const MODES: { mode: DisplayMode; label: string; title: string }[] = [
  { mode: 'wireframe', label: 'W', title: 'Wireframe' },
  { mode: 'stress', label: 'σ', title: 'Stress Ratio' },
  { mode: 'displacement', label: 'δ', title: 'Displacement' },
  { mode: 'failure', label: 'F', title: 'Pass/Fail' },
];

export default function ViewportToolbar() {
  const displayMode = useAppStore((s) => s.displayMode);
  const setDisplayMode = useAppStore((s) => s.setDisplayMode);
  const showLabels = useAppStore((s) => s.showLabels);
  const toggleLabels = useAppStore((s) => s.toggleLabels);
  const showLoads = useAppStore((s) => s.showLoads);
  const toggleLoads = useAppStore((s) => s.toggleLoads);
  const showSupports = useAppStore((s) => s.showSupports);
  const toggleSupports = useAppStore((s) => s.toggleSupports);
  const showDeformed = useAppStore((s) => s.showDeformed);
  const toggleDeformed = useAppStore((s) => s.toggleDeformed);
  const deformationScale = useAppStore((s) => s.deformationScale);
  const setDeformationScale = useAppStore((s) => s.setDeformationScale);

  return (
    <div className="viewport-toolbar">
      {/* Display mode buttons */}
      {MODES.map((m) => (
        <button
          key={m.mode}
          className={`viewport-btn ${displayMode === m.mode ? 'active' : ''}`}
          onClick={() => setDisplayMode(m.mode)}
          title={m.title}
        >
          {m.label}
        </button>
      ))}

      <div style={{ width: 6 }} />

      {/* Toggle buttons */}
      <button
        className={`viewport-btn ${showLabels ? 'active' : ''}`}
        onClick={toggleLabels}
        title="Node Labels"
      >
        #
      </button>
      <button
        className={`viewport-btn ${showLoads ? 'active' : ''}`}
        onClick={toggleLoads}
        title="Loads"
      >
        ↓
      </button>
      <button
        className={`viewport-btn ${showSupports ? 'active' : ''}`}
        onClick={toggleSupports}
        title="Supports"
      >
        △
      </button>
      <button
        className={`viewport-btn ${showDeformed ? 'active' : ''}`}
        onClick={toggleDeformed}
        title="Deformed Shape overlay"
      >
        δ
      </button>

      {/* Deformation exaggeration. The underlying displacements are the real
          computed values — this only scales how they are DRAWN. */}
      {showDeformed && (
        <>
          <div style={{ width: 6 }} />
          <select
            className="field-select"
            style={{ height: 24, fontSize: 10, padding: '0 4px', width: 'auto' }}
            value={deformationScale}
            onChange={(e) => setDeformationScale(parseInt(e.target.value))}
            title="Visualization scale — not physical deformation. Computed displacements are unchanged."
          >
            {[1, 10, 50, 100, 250].map((s) => (
              <option key={s} value={s}>{s}× visual</option>
            ))}
          </select>
          <span style={{
            fontSize: 9,
            color: '#f59e0b',
            fontFamily: "'JetBrains Mono', monospace",
            marginLeft: 4,
          }}>
            visualization scale — not physical deformation
          </span>
        </>
      )}
    </div>
  );
}
