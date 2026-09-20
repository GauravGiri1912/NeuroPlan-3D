# NeuroPlan-3D — Baseline Checkpoint

Recorded: 2026-09-20

## Backend

- Entry point: `backend/server/main.py` (FastAPI app, mounts 3 routers, `/health`)
- Solver entry point: `backend/server/core/fea/solver.py` — `solve(structure, spec, combination=None, include_self_weight=None, thermal=None, settlements=None, springs=None)`
- Test suite: **621/621 passing** (`pytest -q` from `backend/`, ~6s) — was 429/429 at the
  original Task 0 checkpoint; grew through the dimensionality, model-wiring, IS 800,
  buckling and connection strengthening tasks. This is the figure the Engineering
  Summary reports as its recorded (not live) test count.

### Module layout
- `server/core/fea/` — solver, assembly, elements, boundary, postprocess, validator, load_cases, thermal, springs, nonlinear, dynamics, diagnostics
- `server/core/analysis/` — buckling, sensitivity, explorer, report
- `server/core/codes/` — is800_2007, is800_tension_extended, connections, fatigue, fire
- `server/core/generator/` — topology, space_truss
- `server/core/parser/`, `server/core/repair/`, `server/core/evidence.py`
- `server/models/` — structure.py (domain model), evidence.py
- `server/validation/` — independent validation pipeline (Zenodo steel-truss case, comparison engine, independence scoring)
- `server/api/` — routes.py, validation_routes.py, engineering_routes.py, schemas.py, serializers.py

### API routers (all verified 200 OK over real HTTP)
- `routes.py` (`/api`): `POST /parse`, `POST /pipeline/run`, `POST /pipeline/stream`, `GET /materials`, `GET /sections`
- `validation_routes.py` (`/api/validation`): `GET /steel-truss`
- `engineering_routes.py` (`/api/engineering`): `POST /analyse`, `POST /sensitivity`, `POST /explore`, `POST /what-if`, `POST /report`, `GET /capabilities`, `POST /nonlinear`, `POST /modal`, `POST /seismic`, `POST /fatigue`, `POST /fire`, `POST /springs`

### Current validation state
- `state`: `reference_compared`
- `independence.verdict`: `calibrated`
- `independence.headline`: `REFERENCE COMPARED — NOT INDEPENDENT VALIDATION`

## Frontend

- `tsc -b && vite build`: **passes** (586 modules, no errors)
- `oxlint`: **passes** (clean)
- Engineering UI components: `EngineeringPanel.tsx`, `AdvancedAnalysisPanel.tsx` (nonlinear/modal/seismic/fatigue/fire/springs sub-sections), `ValidationLibraryPanel.tsx`
- Browser-tested previously (Playwright): all six Advanced Analysis sub-sections render and run against live backend, zero console errors

## Notes
- No application code was modified to produce this checkpoint.
- This document did not previously exist; created per Task 0.
