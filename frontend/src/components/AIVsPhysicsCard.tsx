/**
 * NeuroPlan-3D — AI vs. Physics Card
 *
 * Makes the project's core claim ("AI proposes, physics decides") visible
 * and checkable in the UI, instead of just a tagline. Shows the AI's
 * unverified, no-calculation first impression side by side with the real
 * deterministic solver verdict, and calls out disagreement explicitly.
 */
import type { AIOpinionData } from '../types/engineering';

interface Props {
  aiOpinion: AIOpinionData | null;
  physicsPassed: boolean;
  pipelineStage: string;
  wasRepaired: boolean;
}

export default function AIVsPhysicsCard({ aiOpinion, physicsPassed, pipelineStage, wasRepaired }: Props) {
  if (pipelineStage !== 'complete' || !aiOpinion) return null;

  const aiSaysSafe = aiOpinion.verdict === 'likely_safe';
  const disagree = !aiOpinion.agrees_with_physics;

  return (
    <div className="panel-section">
      <div className="panel-section-header">
        <span className="panel-section-title">AI Proposes vs. Physics Decides</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div
          style={{
            padding: '8px 10px',
            borderRadius: 4,
            background: '#1a1c24',
            border: '1px solid #2a2d38',
          }}
        >
          <div style={{ fontSize: 9, letterSpacing: 0.5, color: '#8b919e', marginBottom: 4 }}>
            AI PROPOSAL — unverified interpretation, no calculation
          </div>
          <div style={{
            fontSize: 12, fontWeight: 600,
            color: aiSaysSafe ? '#f59e0b' : aiOpinion.verdict === 'uncertain' ? '#8b919e' : '#f59e0b',
          }}>
            {aiOpinion.verdict.replace('_', ' ').toUpperCase()}
            {' '}
            <span style={{ fontWeight: 400, fontSize: 10, color: '#5c6370' }}>
              ({aiOpinion.confidence} confidence, {aiOpinion.source === 'gemini' ? 'Gemini' : 'heuristic fallback'})
            </span>
          </div>
          <div style={{ fontSize: 10, color: '#8b919e', marginTop: 3, fontStyle: 'italic' }}>
            "{aiOpinion.reasoning}"
          </div>
        </div>

        <div style={{ textAlign: 'center', color: '#3b82f6', fontSize: 12 }}>↓</div>

        <div
          style={{
            padding: '8px 10px',
            borderRadius: 4,
            background: '#1a1c24',
            border: '1px solid #2a2d38',
          }}
        >
          <div style={{ fontSize: 9, letterSpacing: 0.5, color: '#8b919e', marginBottom: 4 }}>
            PHYSICS ANALYSIS — deterministic solver, on the AI's original proposal
          </div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#e1e4ea' }}>
            Direct Stiffness Method
          </div>
        </div>

        <div style={{ textAlign: 'center', color: '#3b82f6', fontSize: 12 }}>↓</div>

        <div
          style={{
            padding: '8px 10px',
            borderRadius: 4,
            background: physicsPassed ? '#132a1c' : '#3d1515',
            border: `1px solid ${physicsPassed ? '#1f4a2e' : '#5c1f1f'}`,
          }}
        >
          <div style={{ fontSize: 9, letterSpacing: 0.5, color: '#8b919e', marginBottom: 4 }}>
            ENGINEERING RESULT — before any repair
          </div>
          <div style={{ fontSize: 12, fontWeight: 600, color: physicsPassed ? '#22c55e' : '#ef4444' }}>
            Configured checks: {physicsPassed ? 'PASS' : 'FAIL'}
          </div>
          {!physicsPassed && wasRepaired && (
            <div style={{ fontSize: 10, color: '#8b919e', marginTop: 3 }}>
              → the solver caught this and the repair loop below fixed it to a
              verified pass. The AI never touched that fix — the solver did.
            </div>
          )}
        </div>

        {disagree ? (
          <div style={{
            padding: '8px 10px',
            borderRadius: 4,
            background: '#3d2a0f',
            border: '1px solid #6b4a15',
            fontSize: 11,
            color: '#fbbf24',
            fontWeight: 600,
          }}>
            ⚠ AI's gut check disagreed with the real physics. This is exactly why the
            structure is never trusted on the AI's word — only the solver's.
          </div>
        ) : (
          <div style={{
            fontSize: 10,
            color: '#5c6370',
            padding: '2px 2px',
          }}>
            AI's guess happened to match this time — but it was never checked, so it
            was never trusted. Every result above comes from the solver, not the AI.
          </div>
        )}
      </div>
    </div>
  );
}
