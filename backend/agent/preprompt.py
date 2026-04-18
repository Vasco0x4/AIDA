"""
Load and enrich the system prompt for a headless agent run.

Mirrors the logic in aida.py:627-705: read Docs/PrePrompt.txt verbatim and
append a short block describing the assessment that the run is tied to.
"""
from __future__ import annotations

import os
from typing import Optional

from models import Assessment
from utils.logger import get_logger

logger = get_logger(__name__)


# Inside the backend container the repo root is /app (WORKDIR); Docs/ is
# copied as part of the image build. When running under uvicorn --reload the
# mount is ./backend:/app, so Docs is not under /app — fall back to the
# sibling directory of /app.
_CANDIDATE_PATHS = (
    "/app/Docs/PrePrompt.txt",
    "/Docs/PrePrompt.txt",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "Docs", "PrePrompt.txt")
    ),
)


def _load_preprompt() -> str:
    for path in _CANDIDATE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as exc:
                logger.warning("Failed to read preprompt", path=path, error=str(exc))
    logger.warning("PrePrompt.txt not found; using empty system prompt")
    return ""


def build_system_prompt(assessment: Assessment, goal: str) -> str:
    """Return the full system prompt for an agent run."""
    base = _load_preprompt()
    context = _assessment_context_block(assessment, goal)
    if not base.endswith("\n"):
        base += "\n"
    return base + context


def _assessment_context_block(assessment: Assessment, goal: str) -> str:
    """Append the assessment-specific context section the model needs."""
    target_domains = ", ".join(assessment.target_domains or []) or "—"
    ip_scopes = ", ".join(assessment.ip_scopes or []) or "—"

    return f"""
## **Assessment Loaded**

**{assessment.name}** (ID: {assessment.id}) - Container: {assessment.container_name or "—"}

- Scope: {assessment.scope or "—"}
- Target domains: {target_domains}
- IP scopes: {ip_scopes}
- Environment: {assessment.environment or "—"}
- Category: {assessment.category or "—"}

## **User Goal**

{goal}

The assessment workspace is ready. Use your standard tools to work with files and execute commands. Persist findings via the AIDA MCP tools.
"""


def get_workspace_cwd(assessment: Optional[Assessment]) -> Optional[str]:
    """Best-effort working directory for the headless `claude` process.

    The backend container doesn't have workspace bind-mounts, so the CLI
    simply runs with cwd=/app. Hook kept as a seam for when we wire up a
    per-assessment workspace mount.
    """
    return None
