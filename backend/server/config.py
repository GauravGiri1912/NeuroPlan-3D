"""
NeuroPlan-3D Backend Configuration
"""
import os

# --- Server ---
HOST = "0.0.0.0"
PORT = 8000
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# --- Gemini API ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# --- FEA Defaults ---
DEFAULT_SAFETY_FACTOR = 1.67
DEFAULT_DISPLACEMENT_RATIO = 300  # L/300
MAX_REPAIR_ITERATIONS = 10
MAX_AREA_INCREASE_FACTOR = 3.0
MAX_HEIGHT_INCREASE_FACTOR = 1.5
MAX_MEMBERS_ADDED = 10

# --- Persistence ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
