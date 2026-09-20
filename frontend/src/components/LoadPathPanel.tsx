/**
 * NeuroPlan-3D — Load Path Trace
 *
 * Follows an applied load into the members that carry it, and into the
 * reactions that ultimately resist it.
 *
 * A truss load has no single route — it distributes through every
 * connected member. So instead of drawing one invented "path", this shows
 * the real transfer at the loaded joint and the check that proves it:
 *
 *     applied force + Σ(member force on joint) = 0
 *
 * If that residual is zero, those members genuinely carry that load.
 * Selecting a path also highlights it in the 3D viewport.
 */
import { useAppStore } from '../stores/appStore';
import type { LoadPathData } from '../types/engineering';

const kN = (n: number) => `${(n / 1000).toFixed(3)} kN`;

export default function LoadPathPanel() {
  const evidence = useAppStore((s) => s.evidence);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const traced = useAppStore((s) => s.tracedLoadNodeId);
  const traceLoad = useAppStore((s) => s.traceLoad);
  const results = useAppStore((s) => s.currentResults());
  const inspect = useAppStore((s) => s.inspect);

  if (pipelineStage !== 'complete' || !evidence || evidence.load_paths.length === 0) return null;

  const paths = evidence.load_paths;
  const active = paths.find((p) => p.node_id === traced) ?? null;

  const totalApplied = paths.reduce(
    (acc, p) => ({
      fx: acc.fx + p.applied_fx,
      fy: acc.fy + p.applied_fy,
      fz: acc.fz + p.applied_fz,
    }),
    { fx: 0, fy: 0, fz: 0 },
  );
  const totalReaction = (results?.reactions ?? []).reduce(
    (acc, r) => ({ fx: acc.fx + r.rx, fy: acc.fy + r.ry, fz: acc.fz + r.rz }),
    { fx: 0, fy: 0, fz: 0 },
  );

  return (
    <div className="panel-section">
      <div className="panel-section-header">
        <span className="panel-section-title">Trace Load</span>
        <span style={{ fontSize: 9, color: '#5c6370' }}>
          {paths.length} applied load{paths.length === 1 ? '' : 's'}
        </span>
      </div>

      {/* Load selector */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
        {paths.map((p) => (
          <button
            key={p.node_id}
            className={`btn btn-sm ${traced === p.node_id ? 'btn-primary' : ''}`}
            style={{ fontSize: 10 }}
            onClick={() => traceLoad(traced === p.node_id ? null : p.node_id)}
            title={`Trace the load applied at node ${p.node_id}`}
          >
            Node {p.node_id}
          </button>
        ))}
        {traced !== null && (
          <button className="btn btn-sm" style={{ fontSize: 10 }} onClick={() => traceLoad(null)}>
            Clear
          </button>
        )}
      </div>

      {/* Global chain: applied → reactions */}
      <div style={{
        fontSize: 10,
        fontFamily: "'JetBrains Mono', monospace",
        color: '#8b919e',
        padding: '6px 8px',
        background: '#12141a',
        border: '1px solid #2a2d38',
        borderRadius: 3,
        marginBottom: 6,
      }}>
        <div style={{ color: '#5c6370' }}>ALL LOADS → ALL REACTIONS</div>
        <Line label="Applied ΣF" v={totalApplied} />
        <Line label="Reactions ΣR" v={totalReaction} />
        <Line
          label="Residual"
          v={{
            fx: totalApplied.fx + totalReaction.fx,
            fy: totalApplied.fy + totalReaction.fy,
            fz: totalApplied.fz + totalReaction.fz,
          }}
          highlight
        />
      </div>

      {active ? (
        <ActivePath path={active} onInspect={inspect} />
      ) : (
        <div style={{ fontSize: 10, color: '#5c6370' }}>
          Select a load above to trace it through the structure.
        </div>
      )}
    </div>
  );
}

function ActivePath({ path, onInspect }: {
  path: LoadPathData;
  onInspect: (kind: 'node' | 'member', id: number) => void;
}) {
  return (
    <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
      {/* Step 1 — the load */}
      <Step n={1} title={`Load applied at node ${path.node_id}`}>
        <div style={{ color: '#5c6370' }}>
          position ({path.node_x.toFixed(2)}, {path.node_y.toFixed(2)}, {path.node_z.toFixed(2)}) m
        </div>
        <div style={{ color: '#f59e0b' }}>
          Fx {kN(path.applied_fx)} · Fy {kN(path.applied_fy)} · Fz {kN(path.applied_fz)}
        </div>
      </Step>

      {/* Step 2 — members carrying it away */}
      <Step n={2} title={`Carried by ${path.members.length} connected members`}>
        {path.members.map((m) => (
          <div
            key={m.member_id}
            onClick={() => onInspect('member', m.member_id)}
            style={{ cursor: 'pointer', padding: '2px 0' }}
            title="Click to inspect this member"
          >
            <span style={{ color: '#3b82f6' }}>M{m.member_id}</span>
            <span style={{ color: '#5c6370' }}> → node {m.other_node_id}  </span>
            <span style={{ color: m.axial_force >= 0 ? '#22c55e' : '#f59e0b' }}>
              N {kN(m.axial_force)} {m.axial_force >= 0 ? '(T)' : '(C)'}
            </span>
            <div style={{ color: '#5c6370', paddingLeft: 12 }}>
              c=({m.lx.toFixed(3)}, {m.ly.toFixed(3)}, {m.lz.toFixed(3)}) ·
              F→joint ({kN(m.fx_on_joint)}, {kN(m.fy_on_joint)}, {kN(m.fz_on_joint)})
            </div>
          </div>
        ))}
      </Step>

      {/* Step 3 — the check that proves it */}
      <Step n={3} title="Joint equilibrium check">
        <div style={{ color: '#5c6370' }}>applied + Σ(member force on joint) = 0</div>
        <Line
          label="Residual"
          v={{
            fx: path.joint_residual_fx,
            fy: path.joint_residual_fy,
            fz: path.joint_residual_fz,
          }}
        />
        <div style={{
          color: path.joint_equilibrium_passed ? '#22c55e' : '#ef4444',
          fontWeight: 600,
          marginTop: 2,
        }}>
          relative {path.joint_relative_residual.toExponential(2)} ·{' '}
          {path.joint_equilibrium_passed ? 'PASS' : 'FAIL'}
        </div>
        <div style={{ color: '#5c6370', marginTop: 2 }}>
          A zero residual proves these members genuinely carry this load.
        </div>
      </Step>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8, borderLeft: '2px solid #2a2d38', paddingLeft: 8 }}>
      <div style={{ color: '#b8bdc7', marginBottom: 2 }}>
        <span style={{ color: '#3b82f6' }}>{n}.</span> {title}
      </div>
      {children}
    </div>
  );
}

function Line({ label, v, highlight }: {
  label: string;
  v: { fx: number; fy: number; fz: number };
  highlight?: boolean;
}) {
  const fmt = (n: number) =>
    Math.abs(n) < 1 ? `${n.toExponential(2)} N` : kN(n);
  return (
    <div style={{ color: highlight ? '#22c55e' : '#8b919e' }}>
      {label}: X {fmt(v.fx)} · Y {fmt(v.fy)} · Z {fmt(v.fz)}
    </div>
  );
}
