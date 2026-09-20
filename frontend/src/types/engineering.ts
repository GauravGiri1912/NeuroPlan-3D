/**
 * NeuroPlan-3D — Core Engineering Types
 *
 * Mirrors the backend data models for type-safe frontend consumption.
 */

// ─────────────────────────────────────────────
// Structure
// ─────────────────────────────────────────────

export interface NodeData {
  id: number;
  x: number;
  y: number;
  z: number;
}

export interface SectionData {
  outer_diameter: number;
  wall_thickness: number;
  area: number;
  moment_of_inertia: number;
}

export interface MemberData {
  id: number;
  node_i: number;
  node_j: number;
  material_key: string;
  section: SectionData;
}

export interface SupportData {
  node_id: number;
  support_type: string;
  dx: boolean;
  dy: boolean;
  dz: boolean;
}

export interface LoadData {
  node_id: number;
  fx: number;
  fy: number;
  fz: number;
}

export interface StructureData {
  nodes: NodeData[];
  members: MemberData[];
  supports: SupportData[];
  loads: LoadData[];
}

// ─────────────────────────────────────────────
// Analysis Results
// ─────────────────────────────────────────────

export interface MemberResultData {
  member_id: number;
  axial_force: number;
  axial_force_kn: number;
  stress: number;
  stress_mpa: number;
  stress_ratio: number;
  allowable_stress_mpa: number;
  status: 'ok' | 'overstressed' | 'buckling_risk';
  euler_buckling_load: number;
}

export interface NodeResultData {
  node_id: number;
  dx: number;
  dy: number;
  dz: number;
  total_displacement_mm: number;
}

export interface ReactionData {
  node_id: number;
  rx: number;
  ry: number;
  rz: number;
}

export interface FailureInfoData {
  failure_type: string;
  member_id: number | null;
  node_id: number | null;
  actual_value: number;
  limit_value: number;
  ratio: number;
  description: string;
}

export interface DiagnosisData {
  passed: boolean;
  failures: FailureInfoData[];
  max_stress_ratio: number;
  max_displacement_mm: number;
  failed_member_count: number;
  failed_node_count: number;
}

export interface EquilibriumData {
  residual_fx: number;
  residual_fy: number;
  residual_fz: number;
  residual_mx: number;
  residual_my: number;
  residual_mz: number;
  max_residual: number;
  max_moment_residual: number;
  load_magnitude: number;
  moment_magnitude: number;
  relative_residual: number;
  relative_moment_residual: number;
  tolerance: number;
  passed: boolean;
}

// ─────────────────────────────────────────────
// Engineering evidence & traceability
// ─────────────────────────────────────────────

export type CheckStatus = 'pass' | 'fail' | 'not_available' | 'info';

export interface ProvenanceInputData {
  label: string;
  value: number;
  units: string;
}

export interface ProvenanceData {
  metric: string;
  label: string;
  value: number;
  units: string;
  source_type: 'member' | 'node' | 'reaction' | 'system';
  source_id: number | null;
  source_detail: string;
  equation: string;
  inputs: ProvenanceInputData[];
  note: string;
}

export interface VerificationItemData {
  key: string;
  category: string;
  label: string;
  status: CheckStatus;
  actual_display: string;
  limit_display: string;
  units: string;
  source: string;
  detail: string;
  actual_value: number | null;
  limit_value: number | null;
}

export interface BenchmarkData {
  case: string;
  quantity: string;
  neuroplan_value: number;
  reference_value: number;
  units: string;
  absolute_difference: number;
  relative_difference: number;
  tolerance_relative: number;
  reference_source: string;
  derivation: string;
  status: CheckStatus;
}

export interface AssumptionData {
  topic: string;
  modeled: boolean;
  description: string;
  implication: string;
}

export interface SimulationRecordData {
  simulation_id: string;
  timestamp_utc: string;
  software_version: string;
  solver_method: string;
  solver_backend: string;
  node_count: number;
  member_count: number;
  dof_per_node: number;
  total_dof: number;
  support_count: number;
  load_count: number;
  material_keys: string[];
  section_keys: string[];
  iteration_count: number;
  warnings: string[];
}

export interface LoadPathMemberData {
  member_id: number;
  other_node_id: number;
  axial_force: number;
  stress: number;
  lx: number;
  ly: number;
  lz: number;
  fx_on_joint: number;
  fy_on_joint: number;
  fz_on_joint: number;
}

export interface LoadPathData {
  node_id: number;
  node_x: number;
  node_y: number;
  node_z: number;
  applied_fx: number;
  applied_fy: number;
  applied_fz: number;
  members: LoadPathMemberData[];
  joint_residual_fx: number;
  joint_residual_fy: number;
  joint_residual_fz: number;
  joint_relative_residual: number;
  joint_equilibrium_passed: boolean;
}

export interface EvidenceData {
  provenance: ProvenanceData[];
  verification: VerificationItemData[];
  benchmarks: BenchmarkData[];
  assumptions: AssumptionData[];
  load_paths: LoadPathData[];
  record: SimulationRecordData;
  computation_verified: boolean;
  real_world_validated: boolean;
}

export interface VerificationChecksData {
  solver: boolean;
  geometry: boolean;
  boundary_conditions: boolean;
  equilibrium: boolean;
  stress: boolean;
  displacement: boolean;
  all_passed: boolean;
}

export interface AnalysisResultsData {
  member_results: MemberResultData[];
  node_results: NodeResultData[];
  reactions: ReactionData[];
  diagnosis: DiagnosisData;
  solve_time_ms: number;
  total_weight_kg: number;
  equilibrium: EquilibriumData;
  checks: VerificationChecksData;
  dof_count: number;
  is_spatial: boolean;
}

export interface RepairActionData {
  iteration: number;
  strategy: string;
  target_description: string;
  parameter_changed: string;
  old_value: number;
  new_value: number;
  rationale: string;
}

export interface IterationData {
  iteration_number: number;
  structure: StructureData;
  results: AnalysisResultsData;
  repair_action: RepairActionData | null;
}

// ─────────────────────────────────────────────
// Specification
// ─────────────────────────────────────────────

export interface SpecData {
  structure_type: string;
  is_spatial?: boolean;
  span: number;
  height: number;
  width: number;
  num_panels: number;
  primary_load: number;
  lateral_load_x: number;
  lateral_load_z: number;
  load_description: string;
  material_key: string;
  section_key: string;
  safety_factor: number;
  max_displacement_ratio: number;
  description: string;
  raw_input: string;
  defaults_applied?: string[];
  /** How structure_type's planar/spatial choice was reached — see backend
   *  DimensionalityIntent. Absent only for specs built before this field
   *  existed; never inferred here. */
  dimensionality_intent?: 'explicit_spatial' | 'explicit_planar' | 'conflicting' | 'unspecified';
}

// ─────────────────────────────────────────────
// Pipeline
// ─────────────────────────────────────────────

export type PipelineStage =
  | 'idle'
  | 'parsing'
  | 'parsed'
  | 'generating'
  | 'generated'
  | 'analyzing'
  | 'analyzed'
  | 'repairing'
  | 'complete'
  | 'error';

export interface AIOpinionData {
  verdict: 'likely_safe' | 'likely_unsafe' | 'uncertain';
  confidence: 'low' | 'medium' | 'high';
  reasoning: string;
  source: 'gemini' | 'heuristic_fallback';
  agrees_with_physics: boolean;
}

export interface PipelineResult {
  spec: SpecData;
  iterations: IterationData[];
  verification_status: 'pass' | 'fail' | 'pending';
  summary: Record<string, number>;
  ai_opinion: AIOpinionData | null;
  evidence: EvidenceData | null;
}

// ─────────────────────────────────────────────
// Materials
// ─────────────────────────────────────────────

export interface MaterialData {
  key: string;
  name: string;
  E_gpa: number;
  yield_stress_mpa: number;
  density: number;
}

// ─────────────────────────────────────────────
// Experimental validation (Validation Library)
// ─────────────────────────────────────────────

export interface ValidationDatasetData {
  title: string;
  authors: string[];
  institution: string;
  doi: string;
  license: string;
  publication_date: string;
  version: string;
  repository: string;
  files: string[];
  description: string;
  linked_publication_title: string;
  linked_publication_doi: string;
  linked_publication_url: string;
  retrieved: string;
}

export interface ValidationCaseData {
  case_id: string;
  title: string;
  description: string;
  load_setup_description: string;
  applicable: boolean;
  inapplicability_reason: string;
  parameter_notes: string[];
}

export interface SensorMappingData {
  sensor_id: string;
  node_id: number | null;
  member_id: number | null;
  dof: string;
  status: string;
  reasoning: string;
  comparable: boolean;
  incomparable_reason: string;
}

export interface ValidationComparisonData {
  sensor_id: string;
  node_id: number | null;
  quantity: string;
  experimental_value: number;
  neuroplan_value: number;
  units: string;
  absolute_error: number;
  relative_error: number | null;
  mapping_status: string;
  mapping_note: string;
}

export interface ValidationSummaryData {
  n_points: number;
  mae: number | null;
  rmse: number | null;
  max_absolute_error: number | null;
  max_relative_error: number | null;
  r_squared: number | null;
  r_squared_note: string;
  uncertainty_note: string;
}

export interface ModelParameterData {
  name: string;
  role: string;
  status: string;
  selected_using_measurements: boolean;
  value_summary: string;
  source_reference: string;
  note: string;
}

/** Calibration-vs-validation verdict (ASME V&V 10 / NAFEMS). */
export interface IndependenceData {
  verdict: 'independent' | 'calibrated' | 'not_assessed';
  headline: string;
  explanation: string;
  standard_reference: string;
  calibrated_parameters: ModelParameterData[];
  independent_parameters: ModelParameterData[];
  missing_roles: string[];
}

export interface ValidationResultData {
  state: string;
  independence: IndependenceData;
  parameters: ModelParameterData[];
  error: string | null;
  dataset: ValidationDatasetData;
  case: ValidationCaseData | null;
  mappings: SensorMappingData[];
  comparisons: ValidationComparisonData[];
  summary: ValidationSummaryData | null;
  criterion_note: string;
  damage_scenarios_note: string;
}

/** Data leakage check between calibration and validation sensor sets. */
export interface DataLeakageCheckData {
  passed: boolean;
  calibration_sensor_ids: string[];
  validation_sensor_ids: string[];
  overlapping_sensor_ids: string[];
  explanation: string;
}

/** Independent validation result with explicit calibration/validation split. */
export interface IndependentValidationData {
  status: string;
  status_label: string;
  // Calibration side
  calibration_case_id: string;
  calibration_description: string;
  calibration_sensor_ids: string[];
  calibration_comparisons: ValidationComparisonData[];
  calibration_summary: ValidationSummaryData | null;
  calibration_independence: IndependenceData;
  // Validation side
  validation_case_id: string;
  validation_description: string;
  validation_sensor_ids: string[];
  validation_comparisons: ValidationComparisonData[];
  validation_summary: ValidationSummaryData | null;
  validation_independence: IndependenceData;
  // Mid-span
  midspan_comparison: ValidationComparisonData | null;
  midspan_is_independent: boolean;
  midspan_note: string;
  // Leakage
  leakage_check: DataLeakageCheckData;
  // Model
  solver_method: string;
  model_parameters: ModelParameterData[];
  calibration_parameters_used: string[];
  validation_data_used_during_calibration: boolean;
  // Limitations
  limitations: string[];
  scientific_explanation: string;
  error: string | null;
}

// ─────────────────────────────────────────────
// Viewport
// ─────────────────────────────────────────────

export type DisplayMode = 'wireframe' | 'stress' | 'displacement' | 'failure';

// ─────────────────────────────────────────────
// Engineering hardening pass (Priorities 1-12)
// ─────────────────────────────────────────────

export interface LoadCaseSummaryData {
  case_type: string;
  name: string;
  supported: boolean;
  active: boolean;
  factor: number;
  resultant_fx: number;
  resultant_fy: number;
  resultant_fz: number;
  n_loads: number;
  formulation: string;
  assumptions: string[];
  limitations: string;
  unsupported_reason: string;
}

export interface SelfWeightSummaryData {
  included: boolean;
  gravity: number;
  total_mass_kg: number;
  total_weight_n: number;
  applied_weight_n: number;
  n_loaded_nodes: number;
  unknown_material_members: number[];
}

export interface LoadSummaryData {
  combination_name: string;
  combination_description: string;
  combination_source: string;
  cases: LoadCaseSummaryData[];
  self_weight: SelfWeightSummaryData | null;
  total_applied_fx: number;
  total_applied_fy: number;
  total_applied_fz: number;
}

export interface StabilityDiagnosticData {
  code: string;
  severity: string;
  title: string;
  explanation: string;
  remedy: string;
  affected_nodes: number[];
  affected_members: number[];
  basis: string;
}

export interface StabilityData {
  n_nodes: number;
  n_members: number;
  n_reaction_components: number;
  n_free_dof: number;
  required_dof: number;
  counting_margin: number;
  counting_satisfied: boolean;
  determinacy: string;
  n_zero_modes: number | null;
  condition_number: number | null;
  eigen_analysis_performed: boolean;
  diagnostics: StabilityDiagnosticData[];
}

/** One member's Euler buckling screening — mirrors backend MemberBucklingScreening. */
export interface MemberBucklingScreeningData {
  member_id: number;
  axial_force: number;
  is_compression: boolean;
  length: number;
  area: number;
  inertia: number;
  E: number;
  k_factor: number;
  effective_length: number;
  radius_of_gyration: number;
  slenderness: number;
  transition_slenderness: number;
  column_class: 'not_compression' | 'short' | 'intermediate' | 'slender';
  euler_critical_load: number;
  euler_critical_stress: number;
  utilisation: number;
  status: 'not_applicable' | 'pass' | 'fail' | 'unconservative' | 'not_modeled';
  euler_applicable: boolean;
  note: string;
}

export interface BucklingScreeningData {
  title: string;
  members: MemberBucklingScreeningData[];
  n_compression: number;
  n_failed: number;
  n_unconservative: number;
  max_slenderness: number;
  governing_member_id: number | null;
  governing_reason: string;
  k_basis: string;
  method_limitations: string[];
  disclaimer: string;
}

/** One IS 800 clause evaluated for one member — mirrors backend CodeCheck. */
export interface CodeCheckData {
  member_id: number;
  clause: string;
  check_name: string;
  equation: string;
  inputs: Record<string, string>;
  demand: number;
  capacity: number;
  unit: string;
  dc_ratio: number;
  status: 'pass' | 'fail' | 'not_applicable' | 'not_supported';
  note: string;
  code: string;
  edition: string;
}

/** Every IS 800 check run for one member — mirrors backend MemberCodeReport. */
export interface MemberCodeReportData {
  member_id: number;
  axial_force: number;
  is_compression: boolean;
  section_class: 'plastic' | 'compact' | 'semi_compact' | 'slender';
  checks: CodeCheckData[];
}

export interface CodeScreeningData {
  title: string;
  code: string;
  edition: string;
  code_title: string;
  members: MemberCodeReportData[];
  n_failed: number;
  max_dc_ratio: number;
  governing_member_id: number | null;
  implemented_clauses: string[];
  unsupported_clauses: string[];
  compliance_disclaimer: string;
}

/** One clause evaluated for one declared connection — mirrors backend ConnectionCheck. */
export interface ConnectionCheckData {
  member_id: number;
  connection_type: 'bolted_shear' | 'fillet_weld' | 'not_defined';
  clause: string;
  check_name: string;
  equation: string;
  inputs: Record<string, string>;
  demand: number;
  capacity: number;
  dc_ratio: number;
  status: 'pass' | 'fail' | 'not_modeled';
  note: string;
  code: string;
  edition: string;
}

/** One member's connection rolled up to its GOVERNING check — mirrors backend ConnectionSummary. */
export interface ConnectionSummaryData {
  member_id: number;
  connection_type: 'bolted_shear' | 'fillet_weld' | 'not_defined';
  governing_check_name: string;
  governing_clause: string;
  demand: number;
  capacity: number;
  dc_ratio: number;
  status: 'pass' | 'fail' | 'not_modeled';
  note: string;
}

export interface ConnectionScreeningData {
  title: string;
  checks: ConnectionCheckData[];
  summaries: ConnectionSummaryData[];
  members_without_connection: number[];
  n_failed: number;
  max_dc_ratio: number;
  governing_member_id: number | null;
  unsupported_checks: string[];
  disclaimer: string;
}

/** Identifies which structure an analysis actually ran on — see backend
 *  engineering_routes._model_meta(). Absent only on responses from before
 *  this field existed; never inferred on the frontend. */
export interface AnalysisModelMeta {
  structure_type: string;
  is_spatial: boolean;
  node_count: number;
  member_count: number;
  spec_provided: boolean;
}

export interface EngineeringAnalysisData {
  model?: AnalysisModelMeta;
  load_summary: LoadSummaryData | null;
  stability: StabilityData | null;
  buckling: BucklingScreeningData;
  code_checks: CodeScreeningData;
  connections: ConnectionScreeningData;
  max_stress_mpa: number;
  max_displacement_mm: number;
  total_weight_kg: number;
  equilibrium_passed: boolean;
}
