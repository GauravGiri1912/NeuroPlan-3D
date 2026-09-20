/**
 * NeuroPlan-3D — Application Store (Zustand)
 *
 * Single store managing all application state:
 * - Specification input
 * - Pipeline execution
 * - Structure data
 * - Analysis results
 * - Viewport display settings
 */
import { create } from 'zustand';
import type {
  SpecData, StructureData, AnalysisResultsData,
  IterationData, PipelineStage, DisplayMode,
  PipelineResult, AIOpinionData, EvidenceData, ValidationResultData,
  EngineeringAnalysisData, IndependentValidationData,
} from '../types/engineering';

const API_BASE = '/api';

/** One controlled connection declaration — mirrors backend BoltedConnectionRequest. */
export interface DeclaredBoltedConnection {
  kind: 'bolted';
  member_id: number;
  bolt_diameter_mm: number;
  bolt_grade: string;
  bolt_count: number;
}

/** Mirrors backend WeldedConnectionRequest. */
export interface DeclaredWeldedConnection {
  kind: 'welded';
  member_id: number;
  weld_size_mm: number;
  weld_length_mm: number;
  shop_weld: boolean;
}

export type DeclaredConnection = DeclaredBoltedConnection | DeclaredWeldedConnection;

export type NavView =
  | 'overview' | 'setup'
  | 'model' | 'results' | 'checks'
  | 'failure-lab' | 'compare' | 'robustness'
  | 'load-cases' | 'diagnostics' | 'sensitivity' | 'buckling' | 'is800' | 'advanced'
  | 'validation' | 'engineering-evidence' | 'report';

interface AppState {
  // ── Navigation (UI shell only — no engineering meaning) ──
  activeNavView: NavView;
  setActiveNavView: (v: NavView) => void;
  // Mobile nav drawer — desktop layout ignores this entirely (CSS-gated).
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;

  // ── Specification ──
  rawInput: string;
  spec: SpecData | null;
  setRawInput: (v: string) => void;
  setSpec: (s: SpecData) => void;
  updateSpec: (partial: Partial<SpecData>) => void;

  // ── Pipeline ──
  pipelineStage: PipelineStage;
  pipelineMessage: string;
  error: string | null;

  // ── Results ──
  iterations: IterationData[];
  currentIterationIndex: number;
  verificationStatus: 'pass' | 'fail' | 'pending';
  summary: Record<string, number>;
  aiOpinion: AIOpinionData | null;
  evidence: EvidenceData | null;
  setCurrentIteration: (i: number) => void;

  // ── Physical explorer (per-category visibility) ──
  visibility: {
    nodes: boolean;
    members: boolean;
    loads: boolean;
    supports: boolean;
    reactions: boolean;
    axes: boolean;
    grid: boolean;
    failures: boolean;
  };
  toggleVisibility: (key: keyof AppState['visibility']) => void;
  isolate: (key: keyof AppState['visibility']) => void;
  showAll: () => void;

  // ── Inspector (click-to-inspect evidence) ──
  inspectorTarget: { kind: 'node' | 'member' | 'load' | 'support'; id: number } | null;
  inspect: (kind: 'node' | 'member' | 'load' | 'support', id: number) => void;
  clearInspector: () => void;
  tracedLoadNodeId: number | null;
  traceLoad: (nodeId: number | null) => void;

  // ── Validation Library (experimental validation, independent of any run) ──
  validationResult: ValidationResultData | null;
  validationLoading: boolean;
  validationError: string | null;
  fetchValidation: () => Promise<void>;

  // ── Independent Validation (calibration vs validation split) ──
  independentValidation: IndependentValidationData | null;
  independentValidationLoading: boolean;
  independentValidationError: string | null;
  fetchIndependentValidation: () => Promise<void>;

  // ── Engineering analysis (load cases, diagnostics, screening) ──
  engineering: EngineeringAnalysisData | null;
  engineeringLoading: boolean;
  engineeringError: string | null;
  engineeringSelfWeight: boolean;
  engineeringThermalDeltaT: number;
  // The spec the cached `engineering` result was computed for. Re-fetched
  // whenever `spec` changes (a new model loaded), not just when the
  // self-weight toggle changes — otherwise switching models would leave
  // Load Cases/Buckling/IS 800 silently showing the previous model's data.
  engineeringSpecRef: SpecData | null;
  engineeringThermalRef: number;
  // A single, controlled connection declaration — matching the project's
  // convention (e.g. Failure Lab's one-controlled-change re-analysis)
  // rather than a general connection-editing UI. Declaring one clears
  // the other kind.
  declaredConnection: DeclaredConnection | null;
  engineeringConnectionRef: string;
  setDeclaredConnection: (c: DeclaredConnection | null) => void;
  fetchEngineering: (includeSelfWeight?: boolean, thermalDeltaT?: number) => Promise<void>;

  // ── Viewport ──
  displayMode: DisplayMode;
  showLabels: boolean;
  showLoads: boolean;
  showSupports: boolean;
  showDeformed: boolean;
  deformationScale: number;
  hoveredMemberId: number | null;
  selectedMemberId: number | null;
  setDisplayMode: (m: DisplayMode) => void;
  toggleLabels: () => void;
  toggleLoads: () => void;
  toggleSupports: () => void;
  toggleDeformed: () => void;
  setDeformationScale: (s: number) => void;
  setHoveredMember: (id: number | null) => void;
  setSelectedMember: (id: number | null) => void;

  // ── Failure Lab (member-removal experiment focus, for 3D highlight) ──
  failureLabMemberId: number | null;
  setFailureLabMember: (id: number | null) => void;

  // ── Actions ──
  runPipeline: () => Promise<void>;
  runPipelineWithSpec: (spec: SpecData) => Promise<void>;
  reset: () => void;

  // ── Derived ──
  currentStructure: () => StructureData | null;
  currentResults: () => AnalysisResultsData | null;
}

export const useAppStore = create<AppState>((set, get) => ({
  // ── Navigation ──
  activeNavView: 'overview',
  setActiveNavView: (v) => set({ activeNavView: v, mobileNavOpen: false }),
  mobileNavOpen: false,
  setMobileNavOpen: (open) => set({ mobileNavOpen: open }),

  // ── Specification ──
  rawInput: '',
  spec: null,
  setRawInput: (v) => set({ rawInput: v }),
  setSpec: (s) => set({ spec: s }),
  updateSpec: (partial) => set((state) => ({
    spec: state.spec ? { ...state.spec, ...partial } : null,
  })),

  // ── Pipeline ──
  pipelineStage: 'idle',
  pipelineMessage: '',
  error: null,

  // ── Results ──
  iterations: [],
  currentIterationIndex: 0,
  verificationStatus: 'pending',
  summary: {},
  aiOpinion: null,
  evidence: null,
  visibility: {
    nodes: true, members: true, loads: true, supports: true,
    reactions: false, axes: true, grid: true, failures: false,
  },
  toggleVisibility: (key) => set((s) => ({
    visibility: { ...s.visibility, [key]: !s.visibility[key] },
  })),
  // Isolate shows exactly one category, so a single structural aspect can
  // be examined without everything else drawn over it.
  isolate: (key) => set((s) => ({
    visibility: (Object.keys(s.visibility) as (keyof AppState['visibility'])[])
      .reduce((acc, k) => ({ ...acc, [k]: k === key }), {} as AppState['visibility']),
  })),
  showAll: () => set({
    visibility: {
      nodes: true, members: true, loads: true, supports: true,
      reactions: false, axes: true, grid: true, failures: false,
    },
  }),
  inspectorTarget: null,
  inspect: (kind, id) => set({ inspectorTarget: { kind, id } }),
  clearInspector: () => set({ inspectorTarget: null }),
  tracedLoadNodeId: null,
  traceLoad: (nodeId) => set({ tracedLoadNodeId: nodeId }),

  validationResult: null,
  validationLoading: false,
  validationError: null,
  fetchValidation: async () => {
    if (get().validationLoading || get().validationResult) return;
    set({ validationLoading: true, validationError: null });
    try {
      const response = await fetch(`${API_BASE}/validation/steel-truss`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result: ValidationResultData = await response.json();
      set({ validationResult: result, validationLoading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({ validationLoading: false, validationError: message });
    }
  },
  independentValidation: null,
  independentValidationLoading: false,
  independentValidationError: null,
  fetchIndependentValidation: async () => {
    if (get().independentValidationLoading || get().independentValidation) return;
    set({ independentValidationLoading: true, independentValidationError: null });
    try {
      const response = await fetch(`${API_BASE}/validation/independent`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result: IndependentValidationData = await response.json();
      set({ independentValidation: result, independentValidationLoading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({ independentValidationLoading: false, independentValidationError: message });
    }
  },
  engineering: null,
  engineeringLoading: false,
  engineeringError: null,
  engineeringSelfWeight: true,
  engineeringThermalDeltaT: 0,
  engineeringSpecRef: null,
  engineeringThermalRef: 0,
  declaredConnection: null,
  engineeringConnectionRef: 'null',
  setDeclaredConnection: (c) => set({ declaredConnection: c }),
  fetchEngineering: async (includeSelfWeight, thermalDeltaT) => {
    const withSelfWeight = includeSelfWeight ?? get().engineeringSelfWeight;
    const withThermal = thermalDeltaT ?? get().engineeringThermalDeltaT;
    const currentSpec = get().spec;
    const declared = get().declaredConnection;
    const connectionKey = JSON.stringify(declared);
    // Re-fetch whenever the self-weight choice, thermal ΔT, the declared
    // connection, or the current model has changed since the cached
    // result was computed — otherwise the cache silently misreports the
    // wrong assumption, wrong thermal load, wrong connection, or wrong
    // structure.
    if (get().engineeringLoading) return;
    if (
      get().engineering &&
      withSelfWeight === get().engineeringSelfWeight &&
      withThermal === get().engineeringThermalRef &&
      currentSpec === get().engineeringSpecRef &&
      connectionKey === get().engineeringConnectionRef
    ) return;

    set({ engineeringLoading: true, engineeringError: null,
          engineeringSelfWeight: withSelfWeight,
          engineeringThermalDeltaT: withThermal });
    try {
      const response = await fetch(`${API_BASE}/engineering/analyse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spec: currentSpec,
          include_self_weight: withSelfWeight,
          temperature_change_k: withThermal,
          bolted_connections: declared?.kind === 'bolted' ? [{
            member_id: declared.member_id,
            bolt_diameter_mm: declared.bolt_diameter_mm,
            bolt_grade: declared.bolt_grade,
            bolt_count: declared.bolt_count,
          }] : [],
          welded_connections: declared?.kind === 'welded' ? [{
            member_id: declared.member_id,
            weld_size_mm: declared.weld_size_mm,
            weld_length_mm: declared.weld_length_mm,
            shop_weld: declared.shop_weld,
          }] : [],
        }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail ? String(err.detail) : `HTTP ${response.status}`);
      }
      const result: EngineeringAnalysisData = await response.json();
      set({
        engineering: result,
        engineeringLoading: false,
        engineeringSpecRef: currentSpec,
        engineeringThermalRef: withThermal,
        engineeringConnectionRef: connectionKey,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({ engineeringLoading: false, engineeringError: message });
    }
  },

  setCurrentIteration: (i) => set({ currentIterationIndex: i }),

  // ── Viewport ──
  displayMode: 'stress',
  showLabels: false,
  showLoads: true,
  showSupports: true,
  showDeformed: false,
  deformationScale: 50,
  hoveredMemberId: null,
  selectedMemberId: null,
  setDisplayMode: (m) => set({ displayMode: m }),
  toggleLabels: () => set((s) => ({ showLabels: !s.showLabels })),
  toggleLoads: () => set((s) => ({ showLoads: !s.showLoads })),
  toggleSupports: () => set((s) => ({ showSupports: !s.showSupports })),
  toggleDeformed: () => set((s) => ({ showDeformed: !s.showDeformed })),
  setDeformationScale: (s) => set({ deformationScale: s }),
  setHoveredMember: (id) => set({ hoveredMemberId: id }),
  setSelectedMember: (id) => set({ selectedMemberId: id }),

  failureLabMemberId: null,
  setFailureLabMember: (id) => set({ failureLabMemberId: id }),

  // ── Actions ──
  runPipeline: async () => {
    const { rawInput } = get();
    if (!rawInput.trim()) return;

    set({
      pipelineStage: 'parsing',
      pipelineMessage: 'Extracting engineering parameters...',
      error: null,
      iterations: [],
      verificationStatus: 'pending',
      summary: {},
      aiOpinion: null,
      evidence: null,
      inspectorTarget: null,
      tracedLoadNodeId: null,
    });

    try {
      const response = await fetch(`${API_BASE}/pipeline/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_input: rawInput }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      const result: PipelineResult = await response.json();

      set({
        spec: result.spec,
        iterations: result.iterations,
        currentIterationIndex: result.iterations.length - 1,
        verificationStatus: result.verification_status as 'pass' | 'fail',
        summary: result.summary,
        aiOpinion: result.ai_opinion,
        evidence: result.evidence,
        pipelineStage: 'complete',
        pipelineMessage: result.verification_status === 'pass'
          ? '✓ COMPUTATION VERIFIED'
          : '✗ BEST-EFFORT RESULT',
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({
        pipelineStage: 'error',
        pipelineMessage: '',
        error: message,
      });
    }
  },

  runPipelineWithSpec: async (spec: SpecData) => {
    set({
      pipelineStage: 'generating',
      pipelineMessage: 'Generating structural topology...',
      error: null,
      iterations: [],
      verificationStatus: 'pending',
      summary: {},
      aiOpinion: null,
      evidence: null,
      inspectorTarget: null,
      tracedLoadNodeId: null,
      spec,
    });

    try {
      const response = await fetch(`${API_BASE}/pipeline/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      const result: PipelineResult = await response.json();

      // Contract check. A backend that silently substitutes a different
      // structural system must never be rendered as if it honoured the
      // request — that exact failure (a space-truss request coming back as a
      // planar Pratt truss from a stale backend) shipped once already.
      if (result.spec.structure_type !== spec.structure_type) {
        throw new Error(
          `Backend returned '${result.spec.structure_type}' for a '${spec.structure_type}' ` +
          `request — it is out of date or does not support this structural system. ` +
          `Restart the backend rather than trusting these results.`
        );
      }

      set({
        spec: result.spec,
        iterations: result.iterations,
        currentIterationIndex: result.iterations.length - 1,
        verificationStatus: result.verification_status as 'pass' | 'fail',
        summary: result.summary,
        aiOpinion: result.ai_opinion,
        evidence: result.evidence,
        pipelineStage: 'complete',
        pipelineMessage: result.verification_status === 'pass'
          ? '✓ COMPUTATION VERIFIED'
          : '✗ BEST-EFFORT RESULT',
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({
        pipelineStage: 'error',
        pipelineMessage: '',
        error: message,
      });
    }
  },

  reset: () => set({
    rawInput: '',
    spec: null,
    pipelineStage: 'idle',
    pipelineMessage: '',
    error: null,
    iterations: [],
    currentIterationIndex: 0,
    verificationStatus: 'pending',
    summary: {},
    aiOpinion: null,
    evidence: null,
    inspectorTarget: null,
    tracedLoadNodeId: null,
    hoveredMemberId: null,
    selectedMemberId: null,
  }),

  // ── Derived ──
  currentStructure: () => {
    const { iterations, currentIterationIndex } = get();
    if (iterations.length === 0) return null;
    return iterations[currentIterationIndex]?.structure ?? null;
  },

  currentResults: () => {
    const { iterations, currentIterationIndex } = get();
    if (iterations.length === 0) return null;
    return iterations[currentIterationIndex]?.results ?? null;
  },
}));
