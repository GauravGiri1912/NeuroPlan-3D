/**
 * NeuroPlan-3D — Report Export
 *
 * Downloads the current pipeline result as a self-contained JSON report:
 * the parsed specification, every iteration (structure + full FEA results),
 * the AI's unverified opinion, and the final verdict. Exists so a run's
 * result is a tangible, shareable artifact instead of only living in the
 * browser session.
 */
import type {
  SpecData, IterationData, AIOpinionData, EvidenceData,
} from '../types/engineering';

interface ExportPayload {
  generated_by: string;
  generated_at: string;
  spec: SpecData;
  verification_status: string;
  summary: Record<string, number>;
  ai_opinion: AIOpinionData | null;
  // The evidence package makes the export auditable: provenance, every
  // verification check with its value and limit, live benchmark
  // comparisons, the assumption list, and the simulation record.
  evidence: EvidenceData | null;
  iterations: IterationData[];
}

export function exportReportJSON(payload: Omit<ExportPayload, 'generated_by' | 'generated_at'>) {
  const full: ExportPayload = {
    generated_by: 'NeuroPlan-3D v0.1.0',
    generated_at: new Date().toISOString(),
    ...payload,
  };

  const blob = new Blob([JSON.stringify(full, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const spanLabel = payload.spec ? `${payload.spec.span}m-${payload.spec.structure_type}` : 'report';
  a.href = url;
  a.download = `neuroplan3d-${spanLabel}-${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
