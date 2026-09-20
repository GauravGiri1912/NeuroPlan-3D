/**
 * NeuroPlan-3D — Physical Explorer
 *
 * Per-category visibility for the 3D model, with an "only" action that
 * isolates a single structural aspect so it can be examined without
 * everything else drawn over it.
 *
 * Categories that depend on solver output (reactions, failure locations)
 * are disabled when that output does not exist, rather than silently
 * showing nothing.
 */
import { useAppStore } from '../stores/appStore';

type VisKey = 'nodes' | 'members' | 'loads' | 'supports' | 'reactions' | 'axes' | 'grid' | 'failures';

const CATEGORIES: { key: VisKey; label: string; needsResults?: boolean }[] = [
  { key: 'members', label: 'Members' },
  { key: 'nodes', label: 'Nodes' },
  { key: 'loads', label: 'Loads' },
  { key: 'supports', label: 'Supports' },
  { key: 'reactions', label: 'Reactions', needsResults: true },
  { key: 'failures', label: 'Failure locations', needsResults: true },
  { key: 'axes', label: 'Coordinate axes' },
  { key: 'grid', label: 'Ground grid' },
];

export default function ExplorerPanel() {
  const visibility = useAppStore((s) => s.visibility);
  const toggleVisibility = useAppStore((s) => s.toggleVisibility);
  const isolate = useAppStore((s) => s.isolate);
  const showAll = useAppStore((s) => s.showAll);
  const results = useAppStore((s) => s.currentResults());
  const iterations = useAppStore((s) => s.iterations);

  if (iterations.length === 0) return null;

  const failureCount = results?.diagnosis.failures.length ?? 0;

  return (
    <div className="panel-section">
      <div className="panel-section-header">
        <span className="panel-section-title">Physical Explorer</span>
        <button className="btn btn-sm" style={{ fontSize: 9 }} onClick={showAll}>
          Reset
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {CATEGORIES.map(({ key, label, needsResults }) => {
          const unavailable = needsResults && !results;
          const visible = visibility[key];
          return (
            <div
              key={key}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: 11,
                fontFamily: "'JetBrains Mono', monospace",
                opacity: unavailable ? 0.4 : 1,
              }}
            >
              <label
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  cursor: unavailable ? 'not-allowed' : 'pointer',
                  color: visible ? '#e1e4ea' : '#5c6370',
                }}
              >
                <input
                  type="checkbox"
                  checked={visible}
                  disabled={unavailable}
                  onChange={() => toggleVisibility(key)}
                  style={{ accentColor: '#3b82f6' }}
                />
                {label}
                {key === 'failures' && failureCount > 0 && (
                  <span style={{ color: '#ef4444', fontSize: 9 }}>({failureCount})</span>
                )}
              </label>
              <button
                className="btn btn-sm"
                style={{ fontSize: 9, padding: '1px 6px' }}
                disabled={unavailable}
                onClick={() => isolate(key)}
                title={`Show only ${label.toLowerCase()}`}
              >
                only
              </button>
            </div>
          );
        })}
      </div>

      <div style={{ fontSize: 9, color: '#5c6370', marginTop: 6, lineHeight: 1.4 }}>
        Display modes (wireframe / stress / displacement / failure) are in the
        viewport toolbar.
      </div>
    </div>
  );
}
