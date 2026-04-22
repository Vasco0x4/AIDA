"""
Forward-compat shim for claude-code-sdk.

The SDK's `parse_message` raises `MessageParseError` on unknown message types,
which kills the whole `async for message in query(...)` iterator. Anthropic
ships new message kinds (e.g. `rate_limit_event`) before the SDK catches up,
so we replace the raise with a `SystemMessage` fallback. Our session handler
already renders SystemMessages of any subtype, so the run keeps streaming.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


def _install() -> None:
    try:
        from claude_code_sdk._internal import message_parser as mp
        from claude_code_sdk._errors import MessageParseError
        from claude_code_sdk.types import SystemMessage
    except ImportError:
        # SDK not installed (first boot / tests). Nothing to patch.
        return

    original_parse_message = mp.parse_message

    def safe_parse_message(data):
        try:
            return original_parse_message(data)
        except MessageParseError as exc:
            msg_type = data.get("type") if isinstance(data, dict) else None
            logger.warning(
                "Unknown SDK message type — surfacing as SystemMessage",
                message_type=msg_type,
                error=str(exc),
            )
            return SystemMessage(
                subtype=str(msg_type) if msg_type else "unknown",
                data=data if isinstance(data, dict) else {"raw": repr(data)},
            )

    mp.parse_message = safe_parse_message

    # client.py did `from .message_parser import parse_message` at import
    # time, so it holds its own reference we need to rebind separately.
    try:
        from claude_code_sdk._internal import client as _client
        _client.parse_message = safe_parse_message
    except ImportError:
        pass


_install()
