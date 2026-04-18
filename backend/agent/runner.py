"""
AgentRunner — process-wide registry of in-flight AgentSession tasks.

Owns the mapping {run_id: asyncio.Task} so the API layer can start and
cancel runs without needing to know anything about the session mechanics.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class AgentRunner:
    """Singleton manager for concurrent agent sessions."""

    def __init__(self) -> None:
        self._tasks: Dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        run_id: int,
        assessment_id: int,
        goal: str,
        permission_mode: Optional[str],
        model: Optional[str],
    ) -> None:
        """Schedule a new AgentSession for this run_id."""
        # Import inside the function to avoid a circular import at module
        # load time (session imports ws events which import from websocket
        # package that may not be ready when agent package is first loaded).
        from .session import AgentSession

        async with self._lock:
            if run_id in self._tasks and not self._tasks[run_id].done():
                raise RuntimeError(f"Run {run_id} is already running")

            session = AgentSession(
                run_id=run_id,
                assessment_id=assessment_id,
                goal=goal,
                permission_mode=permission_mode,
                model=model,
            )
            task = asyncio.create_task(session.run(), name=f"agent-run-{run_id}")
            self._tasks[run_id] = task

            # Cleanup reference when the task ends so the dict does not grow
            # without bound over the lifetime of the process.
            task.add_done_callback(lambda _t, rid=run_id: self._tasks.pop(rid, None))

        logger.info("Agent run scheduled", run_id=run_id, assessment_id=assessment_id)

    async def stop(self, run_id: int) -> bool:
        """Cancel the task for run_id. Returns True if a task was cancelled."""
        async with self._lock:
            task = self._tasks.get(run_id)
            if task is None or task.done():
                return False
            task.cancel()

        logger.info("Agent run cancel requested", run_id=run_id)
        return True

    def is_running(self, run_id: int) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()


# Process-wide instance used by the API layer
agent_runner = AgentRunner()
