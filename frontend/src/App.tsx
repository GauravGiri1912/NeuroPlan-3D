/**
 * NeuroPlan-3D — Main Application
 *
 * Shell layout:
 * ┌─────────────────────────────────────────────┐
 * │  Toolbar (brand, project, status, actions)   │
 * ├──────────┬────────────────────────────────────┤
 * │  Nav     │  Active workspace                 │
 * │  Sidebar │  (Overview / Model / Results / …) │
 * ├──────────┴────────────────────────────────────┤
 * │  Status Bar                                  │
 * └─────────────────────────────────────────────┘
 *
 * Every workspace below renders an EXISTING panel component (unchanged
 * internals) — only where they are mounted, and how they are navigated
 * to, has changed. Several destinations intentionally reuse the same
 * underlying panel (documented inline) rather than duplicating logic:
 * Compare reuses Failure Lab (its comparison is a step of that same
 * experiment flow); Buckling and IS 800 reuse the Engineering Analysis
 * panel, auto-opened to that section; Robustness reuses Advanced
 * Analysis, auto-opened to its Robustness block; Engineering Evidence
 * combines Credibility + Provenance, which are both evidence-for-numbers.
 */
import { useAppStore } from './stores/appStore';
import Toolbar from './components/Toolbar';
import NavSidebar from './components/NavSidebar';
import StatusBar from './components/StatusBar';
import ViewWrapper from './components/ViewWrapper';
import OverviewView from './components/OverviewView';
import SpecificationPanel from './components/SpecificationPanel';
import ModelView from './components/ModelView';
import AnalysisPanel from './components/AnalysisPanel';
import CredibilityPanel from './components/CredibilityPanel';
import LoadPathPanel from './components/LoadPathPanel';
import FailureLabPanel from './components/FailureLabPanel';
import EngineeringPanel from './components/EngineeringPanel';
import AdvancedAnalysisPanel from './components/AdvancedAnalysisPanel';
import ValidationLibraryPanel from './components/ValidationLibraryPanel';
import ProvenancePanel from './components/ProvenancePanel';
import SensitivitySection from './components/SensitivitySection';
import ReportView from './components/ReportView';

export default function App() {
  const activeNavView = useAppStore((s) => s.activeNavView);

  return (
    <div className="app-shell">
      <Toolbar />
      <NavSidebar />
      <main className="workspace-main">
        {activeNavView === 'overview' && <OverviewView />}
        {activeNavView === 'setup' && <SpecificationPanel />}
        {activeNavView === 'model' && <ModelView />}
        {activeNavView === 'results' && <AnalysisPanel />}
        {activeNavView === 'checks' && (
          <ViewWrapper group="Primary" title="Checks" subtitle="Computational verification only — not professional engineering certification.">
            <CredibilityPanel />
          </ViewWrapper>
        )}

        {activeNavView === 'failure-lab' && (
          <ViewWrapper group="Challenge" title="Failure Lab" subtitle="Challenge the current design: remove a member, review the evidence, re-analyze a controlled repair.">
            <FailureLabPanel />
          </ViewWrapper>
        )}
        {activeNavView === 'compare' && (
          <ViewWrapper group="Challenge" title="Compare" subtitle="Before/after comparison is produced by running a Failure Lab experiment — reusing that same workspace below rather than a second copy of its state.">
            <FailureLabPanel />
          </ViewWrapper>
        )}
        {activeNavView === 'robustness' && (
          <ViewWrapper group="Challenge" title="Robustness" subtitle="Deterministic Load Robustness — evaluated at fixed load scales using the deterministic solver. Not a probabilistic reliability analysis.">
            <AdvancedAnalysisPanel initialSection="robustness" />
          </ViewWrapper>
        )}

        {activeNavView === 'load-cases' && (
          <ViewWrapper group="Engineering" title="Load Cases">
            <EngineeringPanel initialDetail="loads" />
          </ViewWrapper>
        )}
        {activeNavView === 'diagnostics' && (
          <ViewWrapper group="Engineering" title="Diagnostics" subtitle="Trace how a load travels through the structure, computed from live solver output.">
            <LoadPathPanel />
          </ViewWrapper>
        )}
        {activeNavView === 'sensitivity' && <SensitivitySection />}
        {activeNavView === 'buckling' && (
          <ViewWrapper group="Engineering" title="Buckling">
            <EngineeringPanel initialDetail="buckling" />
          </ViewWrapper>
        )}
        {activeNavView === 'is800' && (
          <ViewWrapper group="Engineering" title="IS 800">
            <EngineeringPanel initialDetail="code" />
          </ViewWrapper>
        )}
        {activeNavView === 'advanced' && (
          <ViewWrapper group="Engineering" title="Advanced Analysis" subtitle="Nonlinear, modal, seismic, fatigue, fire, springs, deterministic load robustness — each run explicitly, on demand.">
            <AdvancedAnalysisPanel />
          </ViewWrapper>
        )}

        {activeNavView === 'validation' && (
          <ViewWrapper group="Evidence" title="Validation">
            <ValidationLibraryPanel />
          </ViewWrapper>
        )}
        {activeNavView === 'engineering-evidence' && (
          <ViewWrapper group="Evidence" title="Engineering Evidence">
            <CredibilityPanel />
            <ProvenancePanel />
          </ViewWrapper>
        )}
        {activeNavView === 'report' && <ReportView />}
      </main>
      <StatusBar />
    </div>
  );
}
