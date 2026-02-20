"""Dev entrypoint to run the API from inside the `backend/` folder.

Why this exists:
- On Windows, running `python -m uvicorn backend.main:app --reload` while your CWD
  is `backend/` can fail because the reload subprocess doesn't have the project
  root on `sys.path`, so `import backend` breaks.

This script forces the project root onto `sys.path` and then starts uvicorn.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_syspath() -> None:
	project_root = Path(__file__).resolve().parent.parent
	root_str = str(project_root)
	if root_str not in sys.path:
		sys.path.insert(0, root_str)


def main() -> None:
	_ensure_project_root_on_syspath()

	import uvicorn

	uvicorn.run(
		"backend.main:app",
		host="127.0.0.1",
		port=8000,
		reload=True,
	)


if __name__ == "__main__":
	main()
