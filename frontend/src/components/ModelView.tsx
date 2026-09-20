/**
 * NeuroPlan-3D — Model Workspace
 *
 * The 3D structure is the primary focus here: the viewport gets the
 * majority of the space, with the existing viewport toolbar, physical
 * explorer (visibility controls) and click-to-inspect overlay attached
 * around it. No new 3D rendering or solver logic — this only re-homes
 * ViewportToolbar / StructuralViewport / Inspector / ExplorerPanel from
 * the old always-on left/right panels into a dedicated workspace.
 */
import ViewportToolbar from './ViewportToolbar';
import StructuralViewport from './StructuralViewport';
import Inspector from './Inspector';
import ExplorerPanel from './ExplorerPanel';
import { useAppStore } from '../stores/appStore';

export default function ModelView() {
  const structure = useAppStore((s) => s.currentStructure());

  return (
    <div className="model-view">
      <div className="viewport-container">
        <ViewportToolbar />
        <StructuralViewport />
        {structure && (
          <div className="viewport-info">
            <span>Orbit: LMB</span>
            <span>Pan: RMB</span>
            <span>Zoom: Scroll</span>
            <span>Click node/member to inspect</span>
          </div>
        )}
        <Inspector />
        {!structure && (
          <div className="empty-state" style={{ position: 'absolute', inset: 0 }}>
            <div className="empty-state-icon">◇</div>
            <div className="empty-state-text">
              No structure loaded yet. Run an analysis from New Analysis to
              populate the 3D model.
            </div>
          </div>
        )}
      </div>
      <div className="model-side">
        <ExplorerPanel />
      </div>
    </div>
  );
}
