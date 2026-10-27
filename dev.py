"""Local development server (not used on Vercel):  python dev.py   ->  http://127.0.0.1:8000

Uses the local JSON store unless SUPABASE_URL is set.  Set EMBED_BACKEND=fake LLM_BACKEND=fake to run without network access.
"""
import importlib.util
from pathlib import Path

import uvicorn

spec = importlib.util.spec_from_file_location("cbti_api", Path(__file__).parent / "api" / "index.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
