"""
FastAPI application package.

The `ai/` package lives at the repository root, next to `backend/`. When the
server is started the normal way (`uvicorn backend.app.main:app` from the repo
root) the root is already on sys.path. This guard covers the other cases -
running pytest from a subdirectory, or an IDE with a different working
directory - so `import ai.llm` never depends on how the process was launched.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
