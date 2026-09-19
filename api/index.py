import sys
from pathlib import Path

# Vercel runs api/index.py with cwd = repo root; backend lives at ./backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

# Vercel's Python runtime discovers a top-level ASGI application named `app`.
# Do not wrap it in Mangum: that adapter is for AWS Lambda event payloads.
