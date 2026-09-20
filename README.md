# NeuroPlan-3D

**Deterministic Physics-Verified 3D Structural Synthesis**

> "AI proposes. Physics decides."

## Overview

NeuroPlan-3D is a prototype engineering tool that turns a natural-language structural
requirement (e.g. *"Design a 20-meter pedestrian bridge truss supporting a 50 kN center
load with A36 steel"*) into a parametric truss, analyzes it with a real Direct
Stiffness Method (DSM) finite element solver, diagnoses failures against code-style
constraints, and runs a bounded rule-based repair loop until the structure passes or the
iteration budget is exhausted.

**Structural systems supported:**

| System | Types | Geometry | Notes |
|---|---|---|---|
| **PLANAR** | Pratt, Howe, Warren | every node at z = 0 | A 2D system solved with the 3D formulation. Needs artificial out-of-plane bracing supports, because no member has out-of-plane stiffness. |
| **SPATIAL** | Box Space Truss | genuine x / y / z | Two vertical trusses separated along Z, joined by transverse members, top/bottom plan bracing and end portal bracing. **Spatially stable through its own members — zero artificial bracing supports.** |

Both are solved by the same engine: a 3D direct-stiffness formulation with **3
translational DOF per node (UX, UY, UZ)**, validated against hand-derived closed-form
solutions on all three axes and on a fully diagonal member.

**Current status: the core pipeline runs end-to-end, verified through the real browser
UI.** Requirement parsing, structural generation, the FEA solver, failure diagnosis, the
repair loop, and the 3D viewport have all been driven live — a headless-browser session
entered the demo requirement, ran the pipeline, and confirmed the verification badge,
key metrics, member table, and 3D truss all rendered correctly with zero console
errors. The solver is additionally validated against an independent hand-derived
statics benchmark, and the UI now surfaces the "AI proposes, physics decides" claim
directly — showing the AI's unverified opinion next to the real solver verdict, not
just asserting it in a tagline. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the full
verification log.

## Problem

Existing structural design tools either require a licensed engineer operating full CAE
software, or are "AI design" tools that hallucinate plausible-looking but physically
unverified structures. There is a gap for a tool that lets a non-expert describe intent
in plain language while guaranteeing every proposed design is checked by a real,
deterministic physics engine — not another model's opinion.

## Solution

Separate the *proposal* stage (AI/NLP extracts parameters) from the *verification* stage
(NumPy/SciPy-based direct stiffness solver, with no AI involvement) so that pass/fail
status is always reproducible and auditable.

## Core Workflow

```
Natural Language Requirement
        ↓
Requirement Extraction (Gemini API, with rule-based fallback)
        ↓
Structured Engineering Specification
        ↓
Parametric Structural Generation (Pratt / Howe / Warren truss)
        ↓
Deterministic FEA (Direct Stiffness Method)
        ↓
Stress / Displacement Analysis
        ↓
Failure Diagnosis
        ↓
Structural Repair (bounded, rule-based)
        ↓
FEA Again
        ↓
Verification (PASS / FAIL)
        ↓
3D Engineering Visualization (React Three Fiber)
```

Every stage above is implemented, wired together in
[`backend/server/api/routes.py`](backend/server/api/routes.py), and has been exercised
live end-to-end via `POST /api/pipeline/run` (see the verification log in
[PROJECT_STATUS.md](PROJECT_STATUS.md)).

## Architecture

```
frontend/  (React + Vite + TypeScript)
  src/stores/appStore.ts        — Zustand store, calls /api/pipeline/run
  src/components/               — Spec input, 3D viewport, analysis panel, status bar
  src/utils/colorScales.ts      — stress/displacement → color mapping for the viewport

backend/   (FastAPI)
  server/api/routes.py          — /api/parse, /api/pipeline/run, /api/pipeline/stream
  server/core/parser/           — NL → EngineeringSpec (Gemini, with regex fallback)
  server/core/generator/        — EngineeringSpec → Structure (Pratt/Howe/Warren topology)
  server/core/fea/              — elements → assembly → boundary → solver → postprocess → validator
  server/core/repair/           — bounded rule-based repair loop
  server/models/structure.py    — shared dataclasses (Node, Member, Material, Section, ...)
  tests/                        — pytest: hand-calculation and regression tests for the solver
```

Frontend and backend talk over a Vite dev-server proxy (`/api` → `http://localhost:8000`).
There is no database — everything is computed per-request and held in frontend memory.

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend framework | React 19 | |
| Build tool | Vite 8 | |
| Language | TypeScript ~6.0 | `npm run build` passes |
| CSS | Tailwind CSS 4 (via `@tailwindcss/vite`) | |
| 3D | Three.js + @react-three/fiber + @react-three/drei | |
| State | Zustand 5 | single global store |
| Backend framework | FastAPI 0.115+ (Uvicorn) | |
| Numerics | NumPy, SciPy | unpinned minimums in `requirements.txt`, Python 3.13-compatible |
| AI/LLM | Google Gemini (`google-genai`, model `gemini-2.5-flash`) | optional — falls back to a regex parser if `GEMINI_API_KEY` is unset |
| Streaming | `sse-starlette` | used for `/api/pipeline/stream` (SSE) |
| Validation | Pydantic 2 | API request/response schemas only; internal models are plain dataclasses |
| Tests | pytest | `backend/tests/` — 7 tests, all passing (including an independent hand-derived validation benchmark) |
| Lint | oxlint (frontend) | passes |

## Current Features

### Functional (verified against a live running backend, not just read from source)
- Direct Stiffness Method solver: element stiffness matrices, direction cosines, global
  assembly, boundary-condition elimination, `numpy.linalg.solve`, member force/stress
  recovery, reaction computation, singularity detection. Cross-checked against a
  hand-calculated single-bar case to 1e-9 relative tolerance.
- Pratt, Howe, and Warren truss topology generators — all three produce fully
  triangulated, statically determinate structures. The generator dispatch has no
  silent fallback: requesting an unimplemented structure type raises an error instead
  of quietly substituting a Pratt truss the user never asked for.
- Constraint validator: stress ratio vs. yield/FOS, displacement vs. L/ratio, simplified
  Euler buckling check.
- Bounded rule-based repair loop — verified live: an intentionally undersized 30m span
  structure (26 initial failures, stress ratio 6.83×) converged to zero failures
  (ratio 0.91×) in 2 iterations.
- Requirement parsing — verified live via `/api/parse` with the Gemini fallback parser
  correctly extracting structure type, span, load, and material from free text.
- Frontend UI is fully wired to real backend responses — no mock or hardcoded result
  data anywhere in the frontend source.
- 3D viewport (React Three Fiber): nodes, members colored by stress ratio or
  displacement, supports, load arrows, deformed-shape overlay, iteration scrubber —
  verified in a real browser session: the truss renders with correct geometry,
  out-of-plane bracing symbols at every interior node, and stress/displacement color
  gradients matching the actual solver output.
- **AI-vs-Physics comparison, shown in the UI.** The AI's unverified "gut check"
  opinion on a proposed structure (no calculation, just an impression from the text)
  is displayed side by side with the real solver verdict, with disagreement called out
  explicitly — making the "AI proposes, physics decides" claim checkable rather than
  asserted. See `backend/server/core/parser/ai_opinion.py`.
- **Solver validated against an independent hand calculation.** A symmetric
  triangular truss solved by hand via the Method of Joints (full derivation in
  `backend/tests/test_validation.py`) matches the solver's output to 1e-6 relative
  tolerance — visible in the UI as a toolbar badge.
- **JSON report export** — one click downloads the full result (spec, every iteration,
  AI opinion, verdict) as a timestamped file.
- **Two rehearsed demo presets** for reliable live presentation without live-typing
  risk: a clean-pass bridge and a deliberately undersized structure that triggers the
  full failure-diagnosis → repair-loop → verified-pass sequence.

### Not implemented
- Project persistence (save/load) — `Project` dataclass and `DATA_DIR` exist but nothing
  reads or writes to it.
- PDF / formatted engineering report generation (JSON export exists).
- Optimization (beyond the bounded rule-based repair loop).

## Engineering / FEA Approach

A 3D pin-jointed Direct Stiffness Method implementation with **3 translational DOF per
node**, so an N-node structure produces a 3N × 3N global system.

**Element formulation.** For a member from node *i* = (xᵢ, yᵢ, zᵢ) to *j* = (xⱼ, yⱼ, zⱼ):

```
dx = xⱼ−xᵢ,  dy = yⱼ−yᵢ,  dz = zⱼ−zᵢ
L  = √(dx² + dy² + dz²)
lx = dx/L,   ly = dy/L,   lz = dz/L      ← direction cosines
c  = [lx, ly, lz]ᵀ
C  = c·cᵀ                                 ← 3×3, rank 1

K_e = (AE/L) · ⎡ C  −C ⎤                  ← 6×6, global coordinates
               ⎣−C   C ⎦
```

The off-diagonal blocks of `C` are what couple the axes — a member with two or three
non-zero direction cosines contributes stiffness across X, Y and Z simultaneously. A
planar truss has `lz = 0` for every member, which is exactly why it needs artificial
z-restraints; the space truss does not.

**Pipeline:**
1. Element matrices from direction cosines ([elements.py](backend/server/core/fea/elements.py))
2. Scattered into the global `K` via a node→DOF map, `base = 3·index` ([assembly.py](backend/server/core/fea/assembly.py))
3. Constrained DOFs identified from independent `dx`/`dy`/`dz` support flags ([boundary.py](backend/server/core/fea/boundary.py))
4. The **free-DOF submatrix** `K_ff` is factorized with Cholesky
   (`scipy.linalg.cho_factor`). For a properly restrained truss `K_ff` is symmetric
   positive definite; a mechanism or rigid-body mode makes it singular and the
   factorization fails — which *is* the mechanism check. A relative-residual test
   then confirms the reduced system was genuinely satisfied.
5. Member forces/stresses, nodal displacements and reactions (`R = K·u − F`) recovered
6. **Global equilibrium verified independently**: `Σ(applied) + Σ(reactions) ≈ 0` on
   each axis, normalized by load magnitude
7. Constraints checked: stress (yield/FOS), displacement (span/ratio), simplified
   Euler buckling for compression members

> **Why not a determinant test for singularity?** Stiffness terms are O(AE/L) ≈ 1e9, so
> `det(K)` for an n-DOF system is O(1e9ⁿ) — it overflows float64 above roughly n = 35
> and returns `inf`/`nan`, silently defeating the check exactly when structures get
> large. Cholesky is scale-invariant, ~5× faster than an SVD, and reuses its
> factorization to solve.

Deterministic and reproducible — same input always produces the same output. Verified
against hand-derived closed-form solutions (see **Testing** below).

## AI Role

The AI (Google Gemini, optional) is used **only** in
[`requirement_parser.py`](backend/server/core/parser/requirement_parser.py) to extract
structured parameters (span, load, material, panel count, etc.) from natural-language
text. It never touches the structural model, the stiffness matrix, or the pass/fail
verdict. If no API key is configured, a regex-based fallback parser is used instead —
the pipeline's physics behavior is identical either way, and the fallback parser has
been verified live.

## Repair Loop

Implemented in [`repair/engine.py`](backend/server/core/repair/engine.py) as a bounded,
rule-based (not ML-based, not gradient-based) loop: it picks the single worst failure,
applies one of two fixed strategies (increase member section, or increase truss height),
re-runs the real FEA solver, and repeats up to `MAX_REPAIR_ITERATIONS` (10) or until two
consecutive iterations show no improvement. Verified live to converge a deliberately
undersized structure in 2 iterations.

## 3D Visualization

React Three Fiber canvas with stress-ratio and displacement color mapping
(blue→green→yellow→red), wireframe/stress/displacement/failure display modes, load
arrows, support symbols, node labels, and a deformed-shape overlay. Reads live data from
the store — verified to receive real solver output via the live backend.

## Project Structure

```
W/
├── backend/
│   ├── requirements.txt
│   ├── tools/               (benchmark_solver.py — CPU timings by structure size)
│   ├── tests/               (pytest — 39 tests incl. 3D closed-form validation)
│   └── server/
│       ├── main.py, config.py
│       ├── api/            (routes, schemas, serializers)
│       ├── core/
│       │   ├── parser/     (NL → spec, plus ai_opinion.py — the "AI gut check")
│       │   ├── generator/  (topology.py — planar; space_truss.py — spatial)
│       │   ├── fea/        (elements, assembly, boundary, solver, postprocess, validator)
│       │   └── repair/     (repair loop)
│       └── models/         (structure.py — shared dataclasses)
└── frontend/
    ├── package.json, vite.config.ts, tsconfig*.json
    └── src/
        ├── components/     (Toolbar, SpecificationPanel, StructuralViewport, ViewportToolbar,
        │                    AnalysisPanel, AIVsPhysicsCard, StatusBar)
        ├── stores/appStore.ts
        ├── types/engineering.ts
        └── utils/           (colorScales.ts, exportReport.ts)
```

No CI configuration or `.env` files exist yet.

## Installation

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate      # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

## Running Locally

```bash
# Backend (from backend/)
uvicorn server.main:app --reload --port 8000

# Frontend (from frontend/, separate terminal)
npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8000`. Open
`http://localhost:5173`.

## Testing

```bash
# Backend — 39 tests
cd backend
pytest tests/ -v
python tools/benchmark_solver.py   # CPU solve times by structure size

# Frontend
cd frontend
npm run build     # type-check + production build
npm run lint       # oxlint
```

| Suite | Tests | Covers |
|---|---|---|
| `test_solver_3d.py` | 11 | **3D formulation validated against closed-form solutions:** axial bars on X, Y and **Z** axes; a fully diagonal member (3-4-12/13) checked for unit direction cosines, cross-axis stiffness coupling and element-matrix equilibrium; a symmetric tripod whose leg forces match `−(P/3)·L/H` by hand; 3-axis global equilibrium; exact BC enforcement; 3D mechanism detection; zero-length rejection; planar regression |
| `test_space_truss.py` | 10 | Spatial generator: two distinct Z planes, members with ≥2 non-zero direction cosines, **stability with zero artificial bracing**, rigid-body-mode suppression, zero-width rejection, lateral loads not discarded, transverse load producing real out-of-plane response |
| `test_solver.py` | 6 | Original planar solver correctness and mechanism detection |
| `test_generator.py` | 6 | Planar generators, Pratt/Howe mirroring, unimplemented-type rejection |
| `test_repair.py` | 5 | Repair strategy selection, iteration budget, **spatial geometry preserved through repair** |
| `test_validation.py` | 1 | Independent Method-of-Joints benchmark |

The Z-axis bar test is the one a 2-DOF planar solver fundamentally cannot pass — it
has no UZ degree of freedom, so a Z-aligned member would have no stiffness at all.

There is no frontend unit/E2E test suite yet (Vitest/Jest/Playwright).

## Example Workflow

Enter: *"Design a 20-meter pedestrian bridge truss supporting a 50 kN center load with
A36 steel"* → parsed into an 8-panel Pratt truss spec → generator produces 18 nodes / 33
members / 18 supports (2 structural + 16 out-of-plane bracing) → solver returns
`verification_status: "pass"`, max stress ratio 0.231, max displacement 5.87mm, support
reactions summing exactly to the 50 kN applied load. Verified twice: once live against
the running server over raw HTTP, and again driving the actual React UI in a real
browser session (verification badge, metrics, member table, and 3D viewport all
confirmed rendering correctly with zero console errors).

## Compute Backend — why CPU, and why not NVIDIA Warp

**CPU (NumPy/SciPy) is the only solver, and that is a measured decision, not an
omission.** `backend/tools/benchmark_solver.py` produces this on the development
machine (median of 5 runs):

| Case | Nodes | Members | DOF | Total (ms) | Assembly | Factor+Solve | K (MB) |
|---|---|---|---|---|---|---|---|
| Planar Pratt (small) | 14 | 25 | 42 | 1.05 | 0.58 | 0.04 | 0.01 |
| Space truss (MVP) | 28 | 80 | 84 | 2.87 | 1.85 | **0.08** | 0.05 |
| Space truss (medium) | 124 | 368 | 372 | 18.33 | 10.38 | 4.25 | 1.06 |
| Space truss (large) | 484 | 1448 | 1452 | 173.90 | 36.40 | 67.90 | 16.09 |
| Space truss (very large) | 1204 | 3608 | 3612 | 683.64 | 138.04 | 657.33 | 99.54 |

At MVP scale the actual matrix factorization takes **0.08 ms**. A GPU round trip
(kernel launch + host↔device transfer) costs on the order of 1–5 ms, so a Warp backend
would make the MVP measurably **slower**, not faster. Even a 400 m, 3612-DOF structure
— far beyond anything the generators are intended to produce — solves in 0.68 s.

Warp was therefore **not added**. No GPU acceleration is claimed anywhere in this
project. If problem sizes ever grow by orders of magnitude, the honest first move is a
sparse solver (`scipy.sparse`), since the stiffness matrix is extremely sparse and is
currently stored dense — that would help long before a GPU would.

> A prior revision used an SVD for mechanism detection, which dominated runtime
> (798 ms of the 1452-DOF case). Switching to Cholesky cut the very-large case from
> **25.5 s → 0.68 s (37×)**. That was a CPU algorithm choice — no GPU involved.

## Scope — what this does and does not do

**Supported:** linear-elastic, small-displacement, pin-jointed 3D truss analysis;
planar and spatial geometry; static point loads in X/Y/Z; independent translational
restraints; stress, displacement and simplified Euler buckling checks; global
equilibrium verification.

**Not supported** (and not claimed):
- Nonlinear material behaviour · Geometric nonlinearity / large displacement
- Dynamic, modal or seismic analysis · Fatigue
- Full buckling analysis (only a simplified Euler check per compression member)
- Bending/frame elements — members carry axial force only
- Connection, joint, weld or bolt design · Foundation analysis
- Wind- or seismic-code compliance · Construction sequencing
- **Professional engineering certification of any kind**

## Current Limitations

- Only one spatial generator (box space truss). Domes, towers and space frames are not
  implemented — and unimplemented types are rejected, never silently substituted.
- The stiffness matrix is stored **dense**. Fine to ~3600 DOF; a sparse solver would be
  the correct next step beyond that.
- No project persistence or PDF/formatted report generation (JSON export exists).
- Frontend test coverage is limited to build/lint (no Vitest/Playwright suite yet).
- Repair strategies are limited to "increase section" / "increase height" — no true
  optimization. Both are dimension-agnostic and verified not to corrupt spatial
  geometry, but neither adds bracing or re-topologizes.
- The AI "gut check" opinion feature is explicitly a demo/credibility feature — it
  never influences the structure or the verdict, and is clearly labeled as unverified
  everywhere it appears (UI and API).

## Remaining Work

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the prioritized (P1–P3) roadmap.

## Future Roadmap

- Broaden test coverage to the generators, repair engine, and API layer.
- Wire up project persistence and a formatted PDF report export.
- Broaden topology types (Howe, K-truss) and consider real optimization.

## Engineering Disclaimer

NeuroPlan-3D is a **computational prototype**, not a certified structural engineering
tool. Its outputs, even though the solver has been verified against hand calculations,
have not been validated against a licensed reference implementation, do not account for
all applicable load cases or code provisions, and must not be used for real-world
structural design, permitting, or construction without independent review and sign-off
by a licensed professional engineer.
