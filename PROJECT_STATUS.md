# NeuroPlan-3D — Project Status

Last updated: 2026-09-19 (true 3D space-truss upgrade). This file is the source of
truth for development sessions. Nothing below is marked functional without having been
read in full and, where possible, executed.

**Update 2026-09-18:** the full pipeline has now been driven through the actual
browser UI (Playwright against the real `npm run dev` + `uvicorn` servers), not just
verified over raw HTTP. See "Browser Verification" below.

**Update 2026-09-19 (differentiation pass):** added the features proposed to make the
project's core claim checkable and credible for a hackathon audience — an AI-vs-physics
comparison surfaced directly in the UI, a solver validation test against an
independently hand-derived classical statics problem (with a visible credibility
badge), JSON report export, rehearsed one-click demo presets, and an empty-state
explainer. See "Differentiation Features Added" below.

**Update 2026-09-19 (drawback-fixing pass):** closed three concrete credibility risks
identified in review: (1) implemented the Howe truss generator, so a user/AI request
for "howe" is now genuinely honored instead of silently substituted with Pratt; (2)
removed dead enum values (`StructureType.K_TRUSS`, `CUSTOM`, `RepairStrategy.ADD_BRACING`)
that implied unshipped functionality, and made the generator dispatch fail loudly
instead of silently defaulting for any unimplemented type; (3) added an explicit scope
note (README + module docstring) that every generated structure is a planar truss, not
a true 3D space truss/frame — stated upfront rather than left to be discovered. Also
added 10 new tests (generator + repair engine), bringing the suite to 17. See
"Drawback-Fixing Pass" below.

**Update 2026-09-19 (true 3D space-truss upgrade):** added genuine spatial structural
analysis. Key audit finding first: **the solver was already a true 3D space-truss
solver** (3 translational DOF per node, full direction-cosine element formulation) —
what was planar was the *geometry generation and input path*, not the physics. See
"True 3D Space-Truss Upgrade" below.

## True 3D Space-Truss Upgrade (2026-09-19)

### Audit finding — the premise was wrong in a useful way

The upgrade request assumed the solver used 2 DOF/node (UX, UY). It did not. Evidence:

| Component | Evidence | Verdict |
|---|---|---|
| `elements.py` | `cx, cy, cz` direction cosines; `C = np.outer(c, c)`; 6×6 element matrix | Already a textbook 3D space-truss element |
| `assembly.py` | `base = 3 * idx`; `n_dof = 3 * len(nodes)` | Already 3 DOF/node |
| `assembly.build_load_vector` | assembles `fx`, `fy`, **and `fz`** | Already 3D |
| `boundary.py` | independent `dx`/`dy`/`dz` flags | Already arbitrary 3D restraints |
| `postprocess.py` | `delta = dot([cx,cy,cz], u_j − u_i)` | Already 3D force recovery |

The decisive proof: the out-of-plane mechanism bug found earlier in this project —
every interior node's z-column in **K** was exactly zero, making the matrix singular —
*can only exist in a solver with real z DOFs*. A 2-DOF solver has no z DOF to go
singular. Rewriting the solver would have destroyed validated working code to rebuild
what already existed, so it was left intact.

### What was actually built

1. **Spatial generator** — `server/core/generator/space_truss.py`. A box/through-type
   space truss: four longitudinal chords forming a rectangular tube, two vertical
   Pratt trusses at z=0 and z=W, transverse members at every panel point, alternating
   plan bracing in the top and bottom planes (non-zero `dx` **and** `dz`), and end
   portal cross bracing (non-zero `dy` **and** `dz`).
   **It is spatially stable through its own members — zero `OUT_OF_PLANE` bracing
   supports**, unlike every planar generator. Supports: pin + roller_x + two new
   `VERTICAL_ONLY` bearings = 7 restraints against 6 rigid-body modes (1 deliberate,
   documented redundancy matching real four-bearing practice).
2. **3D loads end-to-end** — `lateral_load_x` / `lateral_load_z` added to the spec,
   threaded through API → generator → solver → UI. Verified live: a 15 kN transverse
   wind load produces `Rz = −15000 N` exactly, i.e. it is genuinely resisted, not
   discarded.
3. **Global equilibrium verification** (Phase 9) — `compute_equilibrium()` checks
   `Σ(applied) + Σ(reactions) ≈ 0` per axis, normalized by load magnitude. Exposed in
   the API and UI. Measured residuals are ~1e-14 to 1e-15 (machine precision).
4. **Explicit verification breakdown** (Phase 19) — `VerificationChecks` with solver /
   geometry / boundary_conditions / equilibrium / stress / displacement. The API's
   `verification_status` now requires **all six**, not just the stress/displacement
   diagnosis. Rendered as a per-check PASS/FAIL panel in the UI.
5. **Numerical robustness fix (important).** Mechanism detection used
   `np.linalg.det(K_mod)`. Stiffness terms are O(AE/L) ≈ 1e9, so `det` for an n-DOF
   system is O(1e9ⁿ) — it **overflows float64 above roughly n=35 and returns inf/nan**,
   silently defeating the check exactly when structures get large (i.e. in 3D). This
   was observed as a live `RuntimeWarning: overflow encountered in det` on the very
   first space-truss solve. Replaced with Cholesky factorization of the free-DOF
   submatrix `K_ff` (SPD for a properly restrained truss; factorization failure *is*
   the mechanism), plus a relative-residual check. **Side effect: the very-large case
   went from 25.5 s → 0.68 s (37× faster).**
6. **3D-aware parser** — extracts width/depth, space-truss keywords and wind loads, and
   discloses every applied default explicitly (Phase 14).
7. **UI** — PLANAR/SPATIAL grouped system selector, width and lateral-load inputs,
   assumptions-applied panel, computational-checks panel, deformation-scale selector
   labelled "visualization scale — not physical deformation", and camera auto-framing
   so a spatial structure's Z depth is immediately visible instead of edge-on.

### Benchmark — and the NVIDIA Warp decision

`backend/tools/benchmark_solver.py`, median of 5 runs:

| Case | Nodes | Members | DOF | Total (ms) | Assembly | Factor+Solve | K (MB) |
|---|---|---|---|---|---|---|---|
| Planar Pratt (small) | 14 | 25 | 42 | 1.05 | 0.58 | 0.04 | 0.01 |
| Space truss (MVP) | 28 | 80 | 84 | 2.87 | 1.85 | **0.08** | 0.05 |
| Space truss (medium) | 124 | 368 | 372 | 18.33 | 10.38 | 4.25 | 1.06 |
| Space truss (large) | 484 | 1448 | 1452 | 173.90 | 36.40 | 67.90 | 16.09 |
| Space truss (very large) | 1204 | 3608 | 3612 | 683.64 | 138.04 | 657.33 | 99.54 |

**Warp was NOT added.** At MVP scale the factorization takes 0.08 ms; a GPU round trip
costs ~1–5 ms, so a GPU backend would be measurably *slower*. No GPU acceleration is
claimed anywhere. If sizes ever grow by orders of magnitude, a sparse solver
(`scipy.sparse`) is the correct next step — the matrix is very sparse but stored dense.

### Repair loop compatibility (Phase 13)

Evaluated rather than assumed. Both existing strategies are dimension-agnostic:
`increase_section` scales member areas; `increase_height` scales only top-chord
y-coordinates. Verified on an undersized space truss: converged 9.102 → 0.910 in 4
iterations with the z-width preserved exactly (3.5 m throughout) and equilibrium
holding at every iteration. **No spatial-specific repair strategy was invented**,
because none was mathematically necessary.

### Limitations of the 3D work

- One spatial generator only (box space truss) — no domes, towers or space frames.
- Dense stiffness matrix; practical to ~3600 DOF.
- Members remain axial-only (no bending/frame elements).
- Spatial repair does not add bracing or re-topologize.

## Summary

The initial audit found the backend completely non-functional (import bug) and the
frontend production build broken (strict type-check). All P0 blockers plus most P1/P2
items from that audit have been fixed and verified against a real running backend +
real HTTP requests, and then against the real browser UI. A further pass added
features that make the project's technical substance visible and checkable, not just
claimed — see "Differentiation Features Added" below.

## Current Architecture

```
frontend (React 19 + Vite 8 + TS + R3F + Zustand)
        │  fetch('/api/pipeline/run')  — Vite proxy → http://localhost:8000
        ▼
backend (FastAPI)
  routes.py → parser → ai_opinion → generator → fea.solver → repair.engine → serializers → JSON
```

Single-request, stateless pipeline. No database, no persisted projects, no auth.

## Current Technology Stack

| Area | Tech | Version | Required? |
|---|---|---|---|
| Frontend framework | React | 19.2.8 | Required |
| Build tool | Vite | 8.3.0 | Required |
| Language | TypeScript | ~6.0.2 | Required |
| CSS | Tailwind CSS | 4.3.3 | Required |
| 3D engine | Three.js | 0.186 | Required |
| 3D React binding | @react-three/fiber, @react-three/drei | 9.7 / 10.7 | Required |
| State | Zustand | 5.0.15 | Required |
| Lint | oxlint | 1.81 | Optional (dev) |
| Backend framework | FastAPI + Uvicorn | 0.115+ | Required |
| Numerics | NumPy, SciPy | unpinned (`>=`), Python 3.13-compatible | Required |
| Validation | Pydantic | 2.9+ | Required (API layer only) |
| AI/LLM | google-genai (Gemini 2.5 Flash) | 1.14+ | Optional — has rule-based fallback |
| Streaming | sse-starlette | 2.1+ | Required for `/api/pipeline/stream` |
| Testing | pytest | — | `backend/tests/` — 39 tests, all passing |
| Linear algebra | SciPy Cholesky (`cho_factor`/`cho_solve`) | — | Free-DOF factorization; doubles as mechanism detection |
| GPU | **none** | — | NVIDIA Warp evaluated and rejected on measured benchmarks — see below |

## Functionality Matrix

Legend: ✅ FUNCTIONAL 🟡 PARTIALLY FUNCTIONAL 🟠 PLACEHOLDER/MOCK 🔴 BROKEN ⚪ NOT IMPLEMENTED

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | NL requirement input | ✅ | `SpecificationPanel.tsx` textarea, wired to `runPipeline()` |
| 2 | Requirement parsing | ✅ | Verified live: `/api/parse` correctly extracted structure type, span, load, material from free text via the regex fallback |
| 3 | Engineering spec generation | ✅ | Confirmed via live `/api/parse` and `/api/pipeline/run` responses |
| 4 | Structural topology generation | ✅ | Pratt, Howe, and Warren generators verified live — all three produce stable, solvable structures; unimplemented types now raise instead of silently falling back |
| 5 | Node generation | ✅ | `topology.py`, confirmed in live JSON responses |
| 6 | Member generation | ✅ | Confirmed in live JSON responses |
| 7 | Material definition | ✅ | `MATERIAL_LIBRARY`, confirmed via `/api/materials` |
| 8 | Load definition | ✅ | Confirmed in live JSON responses |
| 9 | Boundary conditions | ✅ | PIN / ROLLER_X / OUT_OF_PLANE support types, confirmed live |
| 10 | Direct Stiffness Method | ✅ | Verified against a hand-calculated single-bar case AND an independently hand-derived triangular-truss benchmark (`test_validation.py`) |
| 11 | Global stiffness assembly | ✅ | `assembly.py`, exercised live |
| 12 | Boundary-condition application | ✅ | `boundary.py`, exercised live |
| 13 | Linear system solving | ✅ | `numpy.linalg.solve`, exercised live |
| 14 | Nodal displacement calculation | ✅ | Matches hand calculation to 1e-9 relative tolerance |
| 15 | Member force calculation | ✅ | Matches hand calculation to 1e-9 relative tolerance; matches independent statics benchmark to 1e-6 |
| 16 | Stress calculation | ✅ | Matches hand calculation to 1e-9 relative tolerance |
| 17 | Utilization calculation | ✅ | `stress_ratio` in `validator.py`, confirmed live |
| 18 | Safety-factor calculation | ✅ | `allowable_stress = yield / safety_factor`, confirmed live |
| 19 | Constraint checking | ✅ | Confirmed live (stress, displacement, buckling) |
| 20 | Critical-member detection | ✅ | Failures sorted by ratio descending, confirmed live |
| 21 | Failure diagnosis | ✅ | Confirmed live — 26 real failures diagnosed on an undersized test structure |
| 22 | Repair engine | ✅ | Confirmed live — converged an undersized structure (stress ratio 6.83 → 0.91) in 2 iterations |
| 23 | Repair iteration system | ✅ | Budget/early-stop logic confirmed live |
| 24 | Re-running FEA after repair | ✅ | Confirmed live |
| 25 | Optimization | ⚪ | Repair is rule-based correction, not optimization; no optimizer exists (out of scope for MVP) |
| 26 | 3D structural visualization | ✅ | `StructuralViewport.tsx`, reads live store data |
| 27 | Stress heatmap | ✅ | `stressRatioToColor` |
| 28 | Displacement visualization | ✅ | Displacement display mode wired into `ViewportToolbar.tsx`, colors members by average end-node displacement |
| 29 | Load visualization | ✅ | `LoadArrow` component |
| 30 | Support visualization | ✅ | `SupportSymbol` (pin/roller) |
| 31 | Iteration comparison | ✅ | `AnalysisPanel` before/after rows + iteration scrubber |
| 32 | Verification status | ✅ | Confirmed live: `"verification_status":"pass"` on a valid structure |
| 33 | Backend API | ✅ | `import server.main` succeeds; live server answers `/health`, `/api/parse`, `/api/materials`, `/api/sections`, `/api/pipeline/run` |
| 34 | Frontend-backend integration | ✅ | Verified via real browser session (Playwright): fetch → backend → response → store → UI render, confirmed working with zero console errors |
| 35 | Project persistence | ⚪ | `Project` dataclass and `DATA_DIR` exist; nothing reads/writes it |
| 36 | Export | ✅ | **Added 2026-09-19** — JSON report export (`exportReport.ts`), verified live to trigger a real browser download |
| 37 | Report generation | 🟡 | JSON export exists; no PDF/formatted report yet |
| 38 | Error handling | ✅ | Confirmed live: a genuine mechanism (1-support 2-node structure) correctly raises `FEASolverError`; API/frontend wiring correct |
| 39 | Automated tests | ✅ | `backend/tests/` — `test_solver_3d.py` (11), `test_space_truss.py` (10), `test_solver.py` (6), `test_generator.py` (6), `test_repair.py` (5), `test_validation.py` (1) — 39 tests, all passing |
| 40 | Demo scenario | ✅ | The UI's own placeholder example returns `verification_status: pass` live; two rehearsed one-click demo presets added for reliable live presentation |
| 41 | AI-vs-physics comparison | ✅ | **Added 2026-09-19** — `ai_opinion.py` + `AIVsPhysicsCard.tsx`, verified live end-to-end |

## Differentiation Features Added (2026-09-19)

Built in response to a direct strategic question: in a 4000+ candidate hackathon where
every team has access to the same AI coding tools, what's actually left to
differentiate on? The answer implemented here: make the project's real technical
substance — the AI/physics separation, the solver's correctness — visible and
checkable in the product itself, not just claimed in a pitch.

1. **AI-vs-Physics comparison, surfaced in the UI.** New backend module
   `server/core/parser/ai_opinion.py` asks the AI for an unverified "gut check"
   opinion on the proposed structure — explicitly no calculation, just an impression
   from the text description — using Gemini if configured, or an intentionally crude
   heuristic fallback otherwise. Returned alongside (never influencing) the real
   solver verdict via a new `ai_opinion` field on `PipelineResultResponse`. The
   frontend (`AIVsPhysicsCard.tsx`) renders both side by side at the top of the
   Analysis Panel and explicitly calls out disagreement. Verified live: the
   repair-loop demo shows the AI's uncertain guess against the physics verdict on its
   *original* proposal ("FAILS VERIFICATION"), with a note explaining the repair loop
   below fixed it — the AI never touched that fix. (A UX bug was found and fixed
   during verification: the card initially showed "FAILS VERIFICATION" directly next
   to the main badge's "STRUCTURE VERIFIED," which read as contradictory — the label
   was corrected to make clear it's the verdict on the pre-repair proposal.)
2. **Solver validated against an independently hand-derived benchmark.**
   `backend/tests/test_validation.py` — a symmetric isosceles triangular truss
   (classic Method-of-Joints problem shape), with the full hand derivation written
   out in the test file's docstring, solved independently of any code in this repo.
   Member forces are area/stiffness-independent for a statically determinate truss,
   so this validates the assembly + boundary-condition + solve + force-recovery
   pipeline against pure statics, decoupled from any material/section assumption.
   Matches to 1e-6 relative tolerance. Surfaced in the UI as a toolbar badge
   ("✓ Solver validated vs. hand calculation") with the exact numbers in its tooltip.
3. **JSON report export.** `frontend/src/utils/exportReport.ts` — one click
   downloads the full result (spec, every iteration, AI opinion, verdict) as a
   timestamped JSON file. Verified live: triggers a real browser download.
4. **Two rehearsed one-click demo presets.** "Demo 1: Clean Pass" and "Demo 2:
   Failure → Repair Loop" in `SpecificationPanel.tsx`, removing live-typing risk
   during an actual presentation. Verified live: Demo 2 reliably reproduces the
   26-failures → repair-loop → verified-pass sequence in 3 iterations.
5. **Empty-state explainer.** The Analysis Panel's empty state (what a judge sees
   before clicking anything) now states the "AI proposes, physics decides" claim
   directly instead of a generic "run the pipeline" placeholder.

All five verified live via a headless-Chromium Playwright session against the real
running app — screenshots confirm correct rendering, zero console errors.

## Test Status

| Test | Command | Result | Notes |
|---|---|---|---|
| Backend dependency install | `pip install -r backend/requirements.txt` (Python 3.13) | ✅ PASS | unpinned `>=` minimums |
| Backend import | `python -c "import server.main"` | ✅ PASS | |
| `pytest tests/` | `pytest tests/ -v` | ✅ 7/7 PASS | includes `test_validation.py` (independent statics benchmark) |
| `npm run build` (frontend) | `npm run build` | ✅ exit 0 | |
| `npm run lint` (frontend) | `npm run lint` | ✅ passes | |
| `npm run dev` (frontend) | `npm run dev` | ✅ starts cleanly | |
| Live pipeline run — demo example | `POST /api/pipeline/run` | ✅ `verification_status: pass` | reactions sum exactly to applied load |
| Live pipeline run — Warren truss | `POST /api/pipeline/run` | ✅ `verification_status: pass` | (was HTTP 422 before the mechanism fix) |
| Live pipeline run — undersized structure | `POST /api/pipeline/run` | ✅ 26 failures → repair loop → 0 failures | ratio 6.83 → 0.91 in 2 iterations |
| Live browser session (Playwright) — full run | headless Chromium against real servers | ✅ | verification badge, metrics, member table, 3D viewport, displacement mode all render correctly, zero console errors |
| Live browser session (Playwright) — new features | headless Chromium against real servers | ✅ | demo presets, AI-vs-physics card, validation badge, export download all confirmed working, zero console errors |

## Browser Verification (2026-09-18)

Drove the actual running UI with a headless-Chromium Playwright script against real
`uvicorn` + `npm run dev` processes (no mocks, no stubs):

1. Loaded `http://localhost:5173` — app shell rendered.
2. Typed the UI's own placeholder example into the Requirement Input textarea.
3. Clicked "Run Pipeline".
4. Waited for the verification badge — it resolved to "✓ STRUCTURE VERIFIED".
5. Read back the Key Metrics panel: max stress ratio 0.231, max displacement 5.87mm,
   total weight 1759.8kg, solve time 6.2ms, 33 members, 1 iteration — matches the raw
   HTTP verification exactly.
6. Member results table populated with all 33 rows.
7. The 3D viewport rendered the actual truss geometry, with out-of-plane bracing
   symbols visible at every interior node and members colored by stress ratio.
8. Toggled the displacement display mode — members shifted to a correct
   red-at-midspan → blue-at-supports gradient matching the real displacement field.
9. Browser console: zero errors, zero warnings.

## Mock / Fake Data Audit

No hardcoded/mock/random result data was found anywhere in the codebase, frontend or
backend. All values originate from a real solve. The AI opinion feature added this
pass is explicitly and visibly labeled as unverified/no-calculation — it is not
presented as an engineering result anywhere in the UI or API.

## Drawback-Fixing Pass (2026-09-19)

A prior review surfaced concrete credibility risks — not hypothetical, things a judge
reading the source or probing the demo could actually catch. Fixed:

1. **Howe truss was silently unimplemented.** The AI extraction prompt explicitly
   offers `"howe"` as a structure type, and the fallback parser detects the word
   "howe" in free text — but `generate_structure`'s dispatch table only had Pratt and
   Warren, so any Howe request silently became a Pratt truss with no indication to
   the user. Fixed by implementing `generate_howe_truss` (mirror-image diagonal
   pattern of Pratt, verified geometrically distinct via
   `test_pratt_and_howe_diagonals_are_mirrored`) and wiring it into the dispatch
   table. Verified live: `POST /api/pipeline/run` with raw input mentioning "howe"
   now returns `"structure_type": "howe"` with a real, distinct, solvable structure
   (33 members, `verification_status: pass`) — previously this silently returned a
   Pratt truss.
2. **Dead enum values implied unshipped functionality.** `StructureType.K_TRUSS`,
   `StructureType.CUSTOM`, and `RepairStrategy.ADD_BRACING` existed in the model but
   were never referenced by any generator or repair strategy — a natural thing for a
   judge reading the source to flag as "features that don't actually exist." Removed
   all three. `generate_structure`'s dispatch no longer silently falls back to Pratt
   for any unrecognized type — it raises a clear `ValueError` naming what's actually
   supported, with a regression test (`test_generate_structure_rejects_unimplemented_type`).
3. **"3D" scope was implied, not stated.** Every generated structure is a planar
   truss (all nodes at z=0) modeled with 3 DOF/node — not a true 3D space
   truss/frame generator. This is a reasonable MVP scope, but wasn't stated anywhere
   in the docs, which is a credibility risk if discovered by a judge instead of
   disclosed upfront. Added an explicit "Scope note on 3D" to the README and to the
   topology generator's module docstring.

Test suite grew from 7 to 17: added `test_generator.py` (6 tests — all three
implemented types produce solvable, reaction-balanced structures; Pratt/Howe diagonal
patterns are verified distinct; the unimplemented-type rejection is regression-tested;
Warren's odd-panel-count handling is covered) and `test_repair.py` (4 tests — strategy
selection for stress-exceeded and displacement-exceeded failures, the no-failure case,
and the repair loop's iteration budget cap).

## Remaining Tasks

### P1 — Required for Working MVP
| Task | Why | Status |
|---|---|---|
| Real browser end-to-end run | Prove the UI→browser→backend round trip, not just raw HTTP | ✅ Done 2026-09-18 |
| Broaden test coverage (API layer, frontend unit/E2E) | 39 tests now cover the solver core, the 3D formulation, all generators, the spatial generator and repair strategy selection; the API layer and frontend still have zero automated coverage | Not done |

### P2 — Important for Hackathon Polish
| Task | Why | Status |
|---|---|---|
| AI-vs-physics comparison in UI | Make the core claim checkable, not just asserted | ✅ Done 2026-09-19 |
| Solver validation badge/test | Credibility artifact for judges | ✅ Done 2026-09-19 |
| JSON export | Tangible deliverable | ✅ Done 2026-09-19 |
| Rehearsed demo presets | Demo reliability | ✅ Done 2026-09-19 |
| PDF/formatted report export | JSON export exists; a formatted print/PDF view would be a stronger deliverable | Not done |
| Code-split the frontend bundle | `npm run build` warns the JS bundle is >500kB (R3F + Three.js) | Not done |

### P3 — Optional / Future
| Task | Why |
|---|---|
| Project persistence (save/load) | `Project`/`DATA_DIR` scaffolding already exists but unused |
| Additional topology types (Howe, K-truss) | Enums already defined, generators not written |
| True optimization pass beyond rule-based repair | Current repair is deliberately simple/bounded |

## Hackathon MVP Definition vs. Current State

Minimum demonstrable pipeline: Input → generation → real FEA → real results → failure
diagnosis → repair → FEA again → verification → 3D visualization → iteration comparison.

All stages verified working end-to-end, including through the real browser UI. On top
of that MVP, the project now has a checkable proof of its core differentiator (AI
opinion vs. physics verdict, shown side by side), a credibility artifact (solver
validated against an independent hand calculation, visible as a toolbar badge), an
export deliverable, and rehearsed demo paths for a live presentation.

## Next Recommended Development Phase

**Phase: "Rehearse and defend."** The product now demonstrates its own differentiator
live. Next: have every team member able to explain, unscripted, why Direct Stiffness
Method (not FEM with bending), what the solver does not handle (buckling beyond
simplified Euler, no dynamic/seismic loads, planar trusses only), and walk through the
`test_validation.py` hand derivation from memory. Then, time permitting: broaden test
coverage to the generator and repair modules, and add a formatted PDF report.

- [x] Fix relative imports in `server/core/**`
- [x] Fix `requirements.txt` pins for Python 3.13
- [x] Fix out-of-plane mechanism in the truss generator
- [x] Fix Warren truss in-plane mechanism
- [x] Fix frontend `tsc` unused-var build errors
- [x] Add backend correctness tests against a hand-calculated truss
- [x] Wire up displacement display mode
- [x] Replace `frontend/README.md` boilerplate
- [x] Manually verify one full pipeline run through the real browser UI
- [x] AI-vs-physics comparison surfaced in the UI
- [x] Solver validated against an independent hand-derived benchmark
- [x] JSON report export
- [x] Rehearsed one-click demo presets
- [x] Empty-state explainer
- [x] Implement Howe truss generator (was silently falling back to Pratt)
- [x] Remove dead enum values (`K_TRUSS`, `CUSTOM`, `ADD_BRACING`) and make dispatch fail loudly
- [x] State the planar-truss (not true 3D space truss) scope explicitly in the docs
- [x] Broaden test coverage — generators and repair engine (7 → 17 tests)
- [x] True 3D space-truss generator with genuine x/y/z geometry
- [x] 3D loads (Fx/Fy/Fz) threaded end-to-end, not discarded
- [x] Global equilibrium verification on all three axes
- [x] Explicit per-check verification breakdown (Phase 19)
- [x] Fix determinant-overflow mechanism check → Cholesky (37× faster on large models)
- [x] PLANAR/SPATIAL distinction in code, API and UI
- [x] Benchmark CPU solver and decide on NVIDIA Warp (rejected, with data)
- [x] 3D validation tests against closed-form solutions (17 → 39 tests)
- [ ] Broaden test coverage further (API layer, frontend unit/E2E)
- [ ] Sparse stiffness matrix (needed only beyond ~3600 DOF)
- [ ] Additional spatial generators (tower, space frame, dome)
- [ ] Formatted PDF report export
- [ ] Code-split the frontend bundle
