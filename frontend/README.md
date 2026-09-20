# NeuroPlan-3D — Frontend

React + Vite + TypeScript client for NeuroPlan-3D. See the project root
[README.md](../README.md) for the full project overview and
[PROJECT_STATUS.md](../PROJECT_STATUS.md) for current status.

## Development

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:8000
```

## Build

```bash
npm run build     # tsc -b && vite build
npm run lint       # oxlint
```

The dev server (`npm run dev`) requires the backend (`backend/`) running on port 8000.
