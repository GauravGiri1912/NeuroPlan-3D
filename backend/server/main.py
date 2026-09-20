"""
NeuroPlan-3D — FastAPI Application Entry Point

Serves the REST API for the structural analysis pipeline.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS
from .api.routes import router
from .api.validation_routes import router as validation_router
from .api.engineering_routes import router as engineering_router


app = FastAPI(
    title="NeuroPlan-3D",
    description="Deterministic Physics-Verified 3D Structural Synthesis",
    version="0.1.0",
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(router)
app.include_router(validation_router)
app.include_router(engineering_router)


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "NeuroPlan-3D", "version": "0.1.0"}
