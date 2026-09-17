import sys
from pathlib import Path

# Vercel runs api/index.py with cwd = repo root; backend lives at ./backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from mangum import Mangum
from app.main import app  # noqa: E402

# Vercel's Python runtime expects a top-level `handler` for ASGI apps
handler = Mangum(app, lifespan="off")
