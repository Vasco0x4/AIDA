"""
Headless Claude agent orchestration for UI-initiated scans.

This package intentionally does not touch the CLI workflow (python3 aida.py);
the CLI path remains a parallel, independent mechanism.
"""
from .runner import AgentRunner, agent_runner
from . import _sdk_compat  # noqa: F401 — monkey-patch side-effect

__all__ = ["AgentRunner", "agent_runner"]
