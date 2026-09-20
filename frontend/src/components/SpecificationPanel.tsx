/**
 * NeuroPlan-3D — Specification Panel (Left Panel)
 *
 * Contains:
 * - Natural language input
 * - Parsed specification form (editable)
 * - Material selector
 * - Section parameters
 * - Constraint settings
 */
import { useState } from 'react';
import { useAppStore } from '../stores/appStore';
import type { SpecData } from '../types/engineering';
import StructuralModelCard from './StructuralModelCard';

// Grouped by structural system. PLANAR types place every node at z=0 (a 2D
// system solved with the 3D formulation); SPATIAL types are genuinely
// three-dimensional geometry.
const STRUCTURE_GROUPS: { group: string; options: { value: string; label: string }[] }[] = [
  {
    group: 'PLANAR (2D geometry)',
    options: [
      { value: 'pratt', label: 'Pratt Truss' },
      { value: 'howe', label: 'Howe Truss' },
      { value: 'warren', label: 'Warren Truss' },
    ],
  },
  {
    group: 'SPATIAL (3D geometry)',
    options: [
      { value: 'space_truss', label: 'Box Space Truss' },
    ],
  },
];

const SPATIAL_TYPES = new Set(['space_truss']);

const MATERIALS = [
  { key: 'A36', label: 'ASTM A36 Steel (250 MPa)' },
  { key: 'A992', label: 'ASTM A992 Steel (345 MPa)' },
  { key: 'AL6061', label: 'Aluminum 6061-T6 (276 MPa)' },
];

const SECTIONS = [
  { key: 'CHS_76x3.2', label: 'CHS 76.2×3.2' },
  { key: 'CHS_89x4', label: 'CHS 88.9×4.0' },
  { key: 'CHS_114x4', label: 'CHS 114.3×4.0' },
  { key: 'CHS_114x6', label: 'CHS 114.3×6.4' },
  { key: 'CHS_141x6', label: 'CHS 141.3×6.4' },
  { key: 'CHS_168x6', label: 'CHS 168.3×6.4' },
  { key: 'CHS_219x8', label: 'CHS 219.1×8.0' },
];

export default function SpecificationPanel() {
  const rawInput = useAppStore((s) => s.rawInput);
  const setRawInput = useAppStore((s) => s.setRawInput);
  const spec = useAppStore((s) => s.spec);
  const pipelineStage = useAppStore((s) => s.pipelineStage);
  const runPipeline = useAppStore((s) => s.runPipeline);
  const runPipelineWithSpec = useAppStore((s) => s.runPipelineWithSpec);
  const reset = useAppStore((s) => s.reset);

  const isRunningDemo = pipelineStage !== 'idle' && pipelineStage !== 'complete' && pipelineStage !== 'error';

  const runSafeBridgeDemo = () => {
    reset();
    setRawInput('Design a 20-meter pedestrian bridge truss supporting a 50 kN center load with A36 steel');
    runPipeline();
  };

  const runRepairDemo = () => {
    reset();
    runPipelineWithSpec({
      structure_type: 'pratt',
      span: 30, height: 2.0, width: 0, num_panels: 6,
      primary_load: 200000, lateral_load_x: 0, lateral_load_z: 0,
      load_description: 'center point load',
      material_key: 'A36', section_key: 'CHS_76x3.2',
      safety_factor: 1.67, max_displacement_ratio: 300,
      description: 'Undersized 30m planar truss — demonstrates failure diagnosis + automatic repair',
      raw_input: '',
    });
  };

  const runSpaceTrussDemo = () => {
    reset();
    runPipelineWithSpec({
      structure_type: 'space_truss',
      span: 24, height: 2.5, width: 4.0, num_panels: 8,
      primary_load: 80000, lateral_load_x: 0, lateral_load_z: 15000,
      load_description: 'distributed load',
      material_key: 'A36', section_key: 'CHS_168x6',
      safety_factor: 1.67, max_displacement_ratio: 300,
      description: '24m box space truss with transverse wind load — true 3D analysis',
      raw_input: '',
    });
  };

  const [showManual, setShowManual] = useState(false);
  const [manualSpec, setManualSpec] = useState<SpecData>({
    structure_type: 'pratt',
    span: 20,
    height: 3.33,
    width: 4.0,
    num_panels: 6,
    primary_load: 50000,
    lateral_load_x: 0,
    lateral_load_z: 0,
    load_description: 'center point load',
    material_key: 'A36',
    section_key: 'CHS_114x6',
    safety_factor: 1.67,
    max_displacement_ratio: 300,
    description: '',
    raw_input: '',
  });

  const isRunning = pipelineStage !== 'idle' && pipelineStage !== 'complete' && pipelineStage !== 'error';

  const handleRunNL = () => {
    if (rawInput.trim()) runPipeline();
  };

  const handleRunSpec = () => {
    runPipelineWithSpec(manualSpec);
  };

  const updateManual = (key: keyof SpecData, value: string | number) => {
    setManualSpec((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="view-content">
      <div className="view-header">
        <div className="text-label">Project</div>
        <h1 className="view-title">New Analysis</h1>
        <div className="view-subtitle">
          Describe a structure in plain language, or fill in the form directly.
        </div>
      </div>

      {/* Demo Presets — rehearsed, reliable inputs for live demos */}
      <div className="panel-section">
        <div className="panel-section-header">
          <span className="panel-section-title">Demo Presets</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button
            className="btn btn-sm"
            disabled={isRunningDemo}
            title="A well-proportioned bridge that verifies immediately"
            onClick={runSafeBridgeDemo}
            style={{ textAlign: 'left' }}
          >
            ▸ Demo 1: Clean Pass (20m bridge)
          </button>
          <button
            className="btn btn-sm"
            disabled={isRunningDemo}
            title="A deliberately undersized truss — shows failure diagnosis and the automatic repair loop converging"
            onClick={runRepairDemo}
            style={{ textAlign: 'left' }}
          >
            ▸ Demo 2: Failure → Repair Loop
          </button>
          <button
            className="btn btn-sm"
            disabled={isRunningDemo}
            title="A genuine 3D box space truss with a transverse wind load — 3 translational DOF per node, members spanning all three axes"
            onClick={runSpaceTrussDemo}
            style={{ textAlign: 'left' }}
          >
            ▸ Demo 3: 3D Space Truss (+ wind)
          </button>
        </div>
      </div>

      {/* Requirement Input */}
      <div className="panel-section">
        <div className="panel-section-header">
          <span className="panel-section-title">Requirement Input</span>
          <button
            className="btn btn-sm"
            onClick={() => setShowManual(!showManual)}
            title={showManual ? 'Use natural language' : 'Use manual form'}
          >
            {showManual ? 'NL' : 'Form'}
          </button>
        </div>

        {!showManual ? (
          <>
            <textarea
              className="field-input"
              placeholder="Design a 20-meter pedestrian bridge truss supporting a 50 kN center load with A36 steel"
              value={rawInput}
              onChange={(e) => setRawInput(e.target.value)}
              rows={4}
              disabled={isRunning}
            />
            <div style={{ fontSize: 10, color: '#5c6370', marginTop: 6 }}>
              Supported structural systems: Pratt, Howe, Warren (2D) · Space Truss (3D).
            </div>
            <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
              <button
                className="btn btn-primary run-action-button"
                onClick={handleRunNL}
                disabled={isRunning || !rawInput.trim()}
                style={{ flex: 1 }}
              >
                {isRunning ? (
                  <><span className="spinner" /> Analyzing...</>
                ) : (
                  '▸ Run Pipeline'
                )}
              </button>
              {pipelineStage !== 'idle' && (
                <button className="btn btn-sm" onClick={reset}>Reset</button>
              )}
            </div>
          </>
        ) : (
          <div style={{ marginTop: 4 }}>
            <ManualSpecForm
              spec={manualSpec}
              onChange={updateManual}
              disabled={isRunning}
            />
            <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
              <button
                className="btn btn-primary run-action-button"
                onClick={handleRunSpec}
                disabled={isRunning}
                style={{ flex: 1 }}
              >
                {isRunning ? (
                  <><span className="spinner" /> Analyzing...</>
                ) : (
                  '▸ Analyze Structure'
                )}
              </button>
              {pipelineStage !== 'idle' && (
                <button className="btn btn-sm" onClick={reset}>Reset</button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Parsed Specification (read-only display after pipeline runs) */}
      {spec && (
        <>
          <StructuralModelCard spec={spec} />
          <div className="panel-section">
            <div className="panel-section-header">
              <span className="panel-section-title">Parsed Specification</span>
            </div>
            <SpecDisplay spec={spec} />
          </div>
        </>
      )}

      {/* Applied defaults — every value the user did not specify is listed
          explicitly rather than silently assumed. Collapsed by default:
          the count is always visible, the detail is one click away. */}
      {spec && spec.defaults_applied && spec.defaults_applied.length > 0 && (
        <AssumptionsSection defaults={spec.defaults_applied} />
      )}

    </div>
  );
}

// ─── Manual Spec Form ───

function ManualSpecForm({ spec, onChange, disabled }: {
  spec: SpecData;
  onChange: (key: keyof SpecData, value: string | number) => void;
  disabled: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div className="field-group">
        <label className="field-label">Structural System</label>
        <select
          className="field-select"
          value={spec.structure_type}
          onChange={(e) => onChange('structure_type', e.target.value)}
          disabled={disabled}
        >
          {STRUCTURE_GROUPS.map((g) => (
            <optgroup key={g.group} label={g.group}>
              {g.options.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {/* Transverse width — only meaningful for a spatial system */}
      {SPATIAL_TYPES.has(spec.structure_type) && (
        <div className="field-group">
          <label className="field-label">Width — transverse, Z (m)</label>
          <input
            type="number"
            className="field-input"
            value={spec.width || 0}
            onChange={(e) => onChange('width', parseFloat(e.target.value) || 0)}
            disabled={disabled}
            step={0.5}
            min={0.5}
          />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        <div className="field-group">
          <label className="field-label">Span (m)</label>
          <input
            type="number"
            className="field-input"
            value={spec.span}
            onChange={(e) => onChange('span', parseFloat(e.target.value) || 0)}
            disabled={disabled}
            step={0.5}
          />
        </div>
        <div className="field-group">
          <label className="field-label">Height (m)</label>
          <input
            type="number"
            className="field-input"
            value={spec.height}
            onChange={(e) => onChange('height', parseFloat(e.target.value) || 0)}
            disabled={disabled}
            step={0.1}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        <div className="field-group">
          <label className="field-label">Panels</label>
          <input
            type="number"
            className="field-input"
            value={spec.num_panels}
            onChange={(e) => onChange('num_panels', parseInt(e.target.value) || 6)}
            disabled={disabled}
            min={4}
            max={20}
          />
        </div>
        <div className="field-group">
          <label className="field-label">Vertical Load −Y (kN)</label>
          <input
            type="number"
            className="field-input"
            value={spec.primary_load / 1000}
            onChange={(e) => onChange('primary_load', (parseFloat(e.target.value) || 0) * 1000)}
            disabled={disabled}
            step={5}
          />
        </div>
      </div>

      {/* Lateral load components — only carried by a spatial system.
          A planar truss has no members with out-of-plane stiffness, so a
          transverse load there would be resisted only by bracing supports. */}
      {SPATIAL_TYPES.has(spec.structure_type) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          <div className="field-group">
            <label className="field-label">Longitudinal +X (kN)</label>
            <input
              type="number"
              className="field-input"
              value={(spec.lateral_load_x || 0) / 1000}
              onChange={(e) => onChange('lateral_load_x', (parseFloat(e.target.value) || 0) * 1000)}
              disabled={disabled}
              step={1}
            />
          </div>
          <div className="field-group">
            <label className="field-label">Transverse +Z (kN)</label>
            <input
              type="number"
              className="field-input"
              value={(spec.lateral_load_z || 0) / 1000}
              onChange={(e) => onChange('lateral_load_z', (parseFloat(e.target.value) || 0) * 1000)}
              disabled={disabled}
              step={1}
            />
          </div>
        </div>
      )}

      <div className="field-group">
        <label className="field-label">Load Type</label>
        <select
          className="field-select"
          value={spec.load_description}
          onChange={(e) => onChange('load_description', e.target.value)}
          disabled={disabled}
        >
          <option value="center point load">Center Point Load</option>
          <option value="distributed load">Distributed Load</option>
        </select>
      </div>

      <div className="field-group">
        <label className="field-label">Material</label>
        <select
          className="field-select"
          value={spec.material_key}
          onChange={(e) => onChange('material_key', e.target.value)}
          disabled={disabled}
        >
          {MATERIALS.map((m) => (
            <option key={m.key} value={m.key}>{m.label}</option>
          ))}
        </select>
      </div>

      <div className="field-group">
        <label className="field-label">Cross Section</label>
        <select
          className="field-select"
          value={spec.section_key}
          onChange={(e) => onChange('section_key', e.target.value)}
          disabled={disabled}
        >
          {SECTIONS.map((s) => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        <div className="field-group">
          <label className="field-label">Safety Factor</label>
          <input
            type="number"
            className="field-input"
            value={spec.safety_factor}
            onChange={(e) => onChange('safety_factor', parseFloat(e.target.value) || 1.67)}
            disabled={disabled}
            step={0.1}
            min={1.0}
          />
        </div>
        <div className="field-group">
          <label className="field-label">Disp. Ratio (L/n)</label>
          <input
            type="number"
            className="field-input"
            value={spec.max_displacement_ratio}
            onChange={(e) => onChange('max_displacement_ratio', parseFloat(e.target.value) || 300)}
            disabled={disabled}
            step={50}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Assumptions (collapsed by default — progressive disclosure) ───

function AssumptionsSection({ defaults }: { defaults: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="panel-section">
      <div
        className="panel-section-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen(!open)}
      >
        <span className="panel-section-title">
          {open ? '▾' : '▸'} {defaults.length} assumption{defaults.length === 1 ? '' : 's'} applied
        </span>
        {!open && <span style={{ fontSize: 10, color: '#3b82f6' }}>Review →</span>}
      </div>
      {open && (
        <div style={{
          fontSize: 10,
          color: '#8b919e',
          lineHeight: 1.5,
          borderLeft: '2px solid #f59e0b',
          paddingLeft: 8,
        }}>
          <div style={{ color: '#f59e0b', marginBottom: 4 }}>
            These were NOT specified — the system chose them:
          </div>
          {defaults.map((d, i) => (
            <div key={i}>• {d.replace(/ \(not specified — default applied\)$/, '')}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Spec Display (Read-only) ───

function SpecDisplay({ spec }: { spec: SpecData }) {
  // Trust the backend's own classification when present — the UI must
  // reflect the solved model, never a guess made from the requested type.
  const spatial = spec.is_spatial ?? SPATIAL_TYPES.has(spec.structure_type);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <SpecRow
        label="System"
        value={spatial ? 'SPACE TRUSS (3D)' : 'PLANAR (2D)'}
        highlight={spatial ? '#22c55e' : undefined}
      />
      <SpecRow label="Type" value={spec.structure_type.replace(/_/g, ' ').toUpperCase()} />
      <SpecRow label="Span (X)" value={`${spec.span.toFixed(1)} m`} />
      <SpecRow label="Height (Y)" value={`${spec.height.toFixed(2)} m`} />
      {spatial && (
        <SpecRow
          label="Width (Z)"
          value={`${(spec.width || 0).toFixed(2)} m`}
          highlight="#22c55e"
        />
      )}
      <SpecRow label="Panels" value={`${spec.num_panels}`} />
      <SpecRow label="Vertical Load" value={`${(spec.primary_load / 1000).toFixed(1)} kN (−Y)`} />
      {spatial && !!spec.lateral_load_x && (
        <SpecRow label="Longitudinal Load" value={`${(spec.lateral_load_x / 1000).toFixed(1)} kN (+X)`} />
      )}
      {spatial && !!spec.lateral_load_z && (
        <SpecRow
          label="Wind Load (Z)"
          value={`${(spec.lateral_load_z / 1000).toFixed(1)} kN (+Z)`}
          highlight="#22c55e"
        />
      )}
      <SpecRow label="Load Type" value={spec.load_description} />
      <SpecRow label="Material" value={spec.material_key} />
      <SpecRow label="Section" value={spec.section_key} />
      <SpecRow label="FOS" value={`${spec.safety_factor.toFixed(2)}`} />
      <SpecRow label="Disp. Limit" value={`L/${spec.max_displacement_ratio.toFixed(0)}`} />
    </div>
  );
}

function SpecRow({ label, value, highlight }: {
  label: string;
  value: string;
  highlight?: string;
}) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '2px 0',
    }}>
      <span className="field-label" style={{ fontSize: 10 }}>{label}</span>
      <span
        className="text-value"
        style={{ fontSize: 11, color: highlight, fontWeight: highlight ? 600 : undefined }}
      >
        {value}
      </span>
    </div>
  );
}
