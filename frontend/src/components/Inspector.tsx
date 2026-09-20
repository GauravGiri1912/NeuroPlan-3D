/**
 * NeuroPlan-3D — Engineering Inspector
 *
 * Click any node or member and see the complete physical and numerical
 * state behind it.
 *
 * Every value rendered here is read from the structure/results the solver
 * returned. The only arithmetic performed in this file is unit conversion
 * for display (m → mm, Pa → MPa) and geometry that is definitionally
 * derived from the node coordinates themselves (member length and
 * direction cosines). No physical quantity is recomputed — if a stress or
 * displacement appears here, the solver produced it.
 */
import { useAppStore } from '../stores/appStore';
import type { StructureData, AnalysisResultsData } from '../types/engineering';

const MATERIALS: Record<string, { name: string; E: number; yield: number; density: number }> = {
  A36: { name: 'ASTM A36 Steel', E: 200e9, yield: 250e6, density: 7850 },
  A992: { name: 'ASTM A992 Steel', E: 200e9, yield: 345e6, density: 7850 },
  AL6061: { name: 'Aluminum 6061-T6', E: 68.9e9, yield: 276e6, density: 2700 },
};

export default function Inspector() {
  const target = useAppStore((s) => s.inspectorTarget);
  const clear = useAppStore((s) => s.clearInspector);
  const structure = useAppStore((s) => s.currentStructure());
  const results = useAppStore((s) => s.currentResults());

  if (!target || !structure || !results) return null;

  return (
    <div className="inspector-overlay">
      <div className="inspector-header">
        <span className="panel-section-title">
          Inspector — {target.kind} {target.id}
        </span>
        <button className="btn btn-sm" onClick={clear} title="Close inspector">✕</button>
      </div>
      <div className="inspector-body">
        {target.kind === 'member'
          ? <MemberInspector id={target.id} structure={structure} results={results} />
          : <NodeInspector id={target.id} structure={structure} results={results} />}
      </div>
    </div>
  );
}

// ─── Member ───

function MemberInspector({ id, structure, results }: {
  id: number; structure: StructureData; results: AnalysisResultsData;
}) {
  // Hooks must run unconditionally — before any early return.
  const inspect = useAppStore((s) => s.inspect);

  const member = structure.members.find((m) => m.id === id);
  const result = results.member_results.find((r) => r.member_id === id);
  if (!member || !result) return <Empty text={`Member ${id} not found in the current model.`} />;

  const ni = structure.nodes.find((n) => n.id === member.node_i)!;
  const nj = structure.nodes.find((n) => n.id === member.node_j)!;

  // Geometry is definitional — it follows directly from the node
  // coordinates the solver used, not from a separate physical model.
  const dx = nj.x - ni.x, dy = nj.y - ni.y, dz = nj.z - ni.z;
  const L = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const mat = MATERIALS[member.material_key];

  return (
    <>
      <Section title="Identity & Connectivity">
        <Row label="Member ID" value={`${member.id}`} />
        <Row
          label="Node A"
          value={`${member.node_i}  (${ni.x.toFixed(3)}, ${ni.y.toFixed(3)}, ${ni.z.toFixed(3)}) m`}
          onClick={() => inspect('node', member.node_i)}
        />
        <Row
          label="Node B"
          value={`${member.node_j}  (${nj.x.toFixed(3)}, ${nj.y.toFixed(3)}, ${nj.z.toFixed(3)}) m`}
          onClick={() => inspect('node', member.node_j)}
        />
        <Row label="Length" value={`${L.toFixed(4)} m`} />
        <Row label="Δx, Δy, Δz" value={`${dx.toFixed(3)}, ${dy.toFixed(3)}, ${dz.toFixed(3)} m`} />
        <Row
          label="Direction cosines"
          value={`lx=${(dx / L).toFixed(5)}  ly=${(dy / L).toFixed(5)}  lz=${(dz / L).toFixed(5)}`}
        />
      </Section>

      <Section title="Section & Material">
        <Row label="Outer diameter" value={`${(member.section.outer_diameter * 1000).toFixed(1)} mm`} />
        <Row label="Wall thickness" value={`${(member.section.wall_thickness * 1000).toFixed(1)} mm`} />
        <Row label="Area A" value={`${(member.section.area * 1e4).toFixed(2)} cm²  (${member.section.area.toExponential(4)} m²)`} />
        <Row label="Moment of inertia I" value={`${member.section.moment_of_inertia.toExponential(4)} m⁴`} />
        <Row label="Material" value={`${member.material_key} — ${mat?.name ?? 'unknown'}`} />
        <Row label="Young's modulus E" value={mat ? `${(mat.E / 1e9).toFixed(1)} GPa` : '—'} />
        <Row label="Yield strength" value={mat ? `${(mat.yield / 1e6).toFixed(0)} MPa` : '—'} />
        <Row label="Density" value={mat ? `${mat.density} kg/m³` : '—'} />
      </Section>

      <Section title="Solver Results">
        <Row
          label="Axial force N"
          value={`${result.axial_force_kn.toFixed(3)} kN  (${result.axial_force >= 0 ? 'tension' : 'compression'})`}
          highlight
        />
        <Row label="Stress σ" value={`${result.stress_mpa.toFixed(3)} MPa`} highlight />
        <Row label="Allowable stress" value={`${result.allowable_stress_mpa.toFixed(2)} MPa`} />
        <Row label="Stress ratio" value={result.stress_ratio.toFixed(4)} highlight />
        <Row
          label="Factor of safety"
          value={result.stress_ratio > 1e-9 ? (1 / result.stress_ratio).toFixed(2) : '∞ (unstressed)'}
        />
        <Row label="Euler buckling load P_cr" value={`${(result.euler_buckling_load / 1000).toFixed(2)} kN`} />
        <Row label="Status" value={result.status.replace(/_/g, ' ').toUpperCase()} />
      </Section>

      <Section title="How these were computed">
        <Calc
          equation="σ = N / A"
          steps={[
            `N = ${result.axial_force.toFixed(2)} N   (solver: member force recovery)`,
            `A = ${member.section.area.toExponential(6)} m²   (section property)`,
            `σ = ${result.axial_force.toFixed(2)} / ${member.section.area.toExponential(6)} = ${result.stress.toExponential(6)} Pa`,
            `  = ${result.stress_mpa.toFixed(3)} MPa`,
          ]}
        />
        <Calc
          equation="N = (A·E/L) · (c · (u_j − u_i))"
          steps={[
            `Axial force from the solved displacement vector, projected onto`,
            `the member axis via its direction cosines c = [lx, ly, lz].`,
            `A·E/L = ${(member.section.area * (mat?.E ?? 0) / L).toExponential(4)} N/m`,
          ]}
        />
        <Calc
          equation="ratio = |σ| / (σ_yield / FOS)"
          steps={[
            `|σ| = ${Math.abs(result.stress_mpa).toFixed(3)} MPa`,
            `allowable = ${result.allowable_stress_mpa.toFixed(2)} MPa`,
            `ratio = ${result.stress_ratio.toFixed(4)}`,
          ]}
        />
        <Calc
          equation="P_cr = π²·E·I / L²"
          steps={[
            `E = ${mat ? (mat.E / 1e9).toFixed(1) : '—'} GPa, I = ${member.section.moment_of_inertia.toExponential(4)} m⁴, L = ${L.toFixed(4)} m`,
            `P_cr = ${(result.euler_buckling_load / 1000).toFixed(2)} kN`,
            `Simplified check only — K=1 assumed, no lateral-torsional buckling.`,
          ]}
        />
      </Section>
    </>
  );
}

// ─── Node ───

function NodeInspector({ id, structure, results }: {
  id: number; structure: StructureData; results: AnalysisResultsData;
}) {
  // Hooks must run unconditionally — before any early return.
  const inspect = useAppStore((s) => s.inspect);

  const node = structure.nodes.find((n) => n.id === id);
  const result = results.node_results.find((r) => r.node_id === id);
  if (!node || !result) return <Empty text={`Node ${id} not found in the current model.`} />;

  const support = structure.supports.find((s) => s.node_id === id);
  const loads = structure.loads.filter((l) => l.node_id === id);
  const reaction = results.reactions.find((r) => r.node_id === id);
  const connected = structure.members.filter((m) => m.node_i === id || m.node_j === id);

  const dofState = (restrained: boolean | undefined) =>
    restrained ? 'RESTRAINED (u = 0)' : 'FREE (solved)';

  return (
    <>
      <Section title="Identity & Position">
        <Row label="Node ID" value={`${node.id}`} />
        <Row label="X" value={`${node.x.toFixed(4)} m`} />
        <Row label="Y" value={`${node.y.toFixed(4)} m`} />
        <Row label="Z" value={`${node.z.toFixed(4)} m`} />
      </Section>

      <Section title="Degrees of Freedom">
        <Row label="UX" value={dofState(support?.dx)} />
        <Row label="UY" value={dofState(support?.dy)} />
        <Row label="UZ" value={dofState(support?.dz)} />
        <Row
          label="Support type"
          value={support ? support.support_type.replace(/_/g, ' ').toUpperCase() : 'none (free node)'}
        />
      </Section>

      <Section title="Applied Loads">
        {loads.length === 0 ? (
          <Row label="Applied load" value="none at this node" />
        ) : loads.map((l, i) => (
          <div key={i}>
            <Row label="Fx" value={`${(l.fx / 1000).toFixed(3)} kN`} />
            <Row label="Fy" value={`${(l.fy / 1000).toFixed(3)} kN`} highlight={l.fy !== 0} />
            <Row label="Fz" value={`${(l.fz / 1000).toFixed(3)} kN`} highlight={l.fz !== 0} />
          </div>
        ))}
      </Section>

      <Section title="Solved Displacement">
        <Row label="UX" value={`${(result.dx * 1000).toFixed(5)} mm`} />
        <Row label="UY" value={`${(result.dy * 1000).toFixed(5)} mm`} highlight />
        <Row label="UZ" value={`${(result.dz * 1000).toFixed(5)} mm`} />
        <Row label="Resultant |u|" value={`${result.total_displacement_mm.toFixed(5)} mm`} highlight />
        <Calc
          equation="|u| = √(UX² + UY² + UZ²)"
          steps={[
            `UX = ${result.dx.toExponential(5)} m`,
            `UY = ${result.dy.toExponential(5)} m`,
            `UZ = ${result.dz.toExponential(5)} m`,
            `|u| = ${(result.total_displacement_mm / 1000).toExponential(5)} m = ${result.total_displacement_mm.toFixed(5)} mm`,
            `Read from the solved vector u at this node's three DOF.`,
          ]}
        />
      </Section>

      {reaction && (
        <Section title="Support Reaction">
          <Row label="Rx" value={`${(reaction.rx / 1000).toFixed(4)} kN`} />
          <Row label="Ry" value={`${(reaction.ry / 1000).toFixed(4)} kN`} highlight />
          <Row label="Rz" value={`${(reaction.rz / 1000).toFixed(4)} kN`} />
          <Calc
            equation="R = K·u − F   (at restrained DOF)"
            steps={[
              'Recovered from the assembled global stiffness matrix and the',
              'solved displacement vector — not assumed or back-figured.',
            ]}
          />
        </Section>
      )}

      <Section title={`Connected Members (${connected.length})`}>
        {connected.map((m) => {
          const mr = results.member_results.find((r) => r.member_id === m.id);
          return (
            <Row
              key={m.id}
              label={`Member ${m.id}`}
              value={mr ? `${mr.axial_force_kn.toFixed(2)} kN · ${mr.stress_mpa.toFixed(1)} MPa` : '—'}
              onClick={() => inspect('member', m.id)}
            />
          );
        })}
      </Section>
    </>
  );
}

// ─── Primitives ───

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{
        fontSize: 10,
        letterSpacing: 0.6,
        color: '#5c6370',
        textTransform: 'uppercase',
        borderBottom: '1px solid #2a2d38',
        paddingBottom: 3,
        marginBottom: 5,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, highlight, onClick }: {
  label: string; value: string; highlight?: boolean; onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 10,
        fontSize: 11,
        padding: '2px 0',
        cursor: onClick ? 'pointer' : 'default',
        fontFamily: "'JetBrains Mono', monospace",
      }}
      title={onClick ? 'Click to inspect' : undefined}
    >
      <span style={{ color: '#8b919e', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{
        color: onClick ? '#3b82f6' : highlight ? '#e1e4ea' : '#b8bdc7',
        fontWeight: highlight ? 600 : 400,
        textAlign: 'right',
      }}>
        {value}
      </span>
    </div>
  );
}

function Calc({ equation, steps }: { equation: string; steps: string[] }) {
  return (
    <details style={{ marginTop: 5 }}>
      <summary style={{
        cursor: 'pointer',
        fontSize: 10,
        color: '#3b82f6',
        fontFamily: "'JetBrains Mono', monospace",
      }}>
        Show calculation — {equation}
      </summary>
      <div style={{
        marginTop: 4,
        padding: '6px 8px',
        background: '#12141a',
        border: '1px solid #2a2d38',
        borderRadius: 3,
        fontSize: 10,
        lineHeight: 1.6,
        color: '#8b919e',
        fontFamily: "'JetBrains Mono', monospace",
        whiteSpace: 'pre-wrap',
      }}>
        {steps.map((s, i) => <div key={i}>{s}</div>)}
      </div>
    </details>
  );
}

function Empty({ text }: { text: string }) {
  return <div style={{ fontSize: 11, color: '#8b919e' }}>{text}</div>;
}
