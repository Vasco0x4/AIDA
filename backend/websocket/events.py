"""
WebSocket Event Types and Helpers
Defines all event types for real-time updates
"""
from enum import Enum
from typing import Any, Dict
from datetime import datetime


class EventType(str, Enum):
    """All WebSocket event types"""

    # Connection events
    CONNECTED = "connected"
    PING = "ping"
    PONG = "pong"

    # Assessment events
    ASSESSMENT_CREATED = "assessment_created"
    ASSESSMENT_UPDATED = "assessment_updated"
    ASSESSMENT_DELETED = "assessment_deleted"

    # Card events (findings, observations, info)
    CARD_ADDED = "card_added"
    CARD_UPDATED = "card_updated"
    CARD_DELETED = "card_deleted"

    # Recon data events
    RECON_ADDED = "recon_added"
    RECON_UPDATED = "recon_updated"
    RECON_DELETED = "recon_deleted"

    # Section events (phases)
    SECTION_UPDATED = "section_updated"

    # ASVS requirement events
    ASVS_UPDATED = "asvs_updated"

    # Command events
    COMMAND_STARTED = "command_started"
    COMMAND_COMPLETED = "command_completed"
    COMMAND_FAILED = "command_failed"
    COMMAND_TIMEOUT = "command_timeout"

    # Credential events
    CREDENTIAL_ADDED = "credential_added"
    CREDENTIAL_UPDATED = "credential_updated"
    CREDENTIAL_DELETED = "credential_deleted"

    # Folder events
    FOLDER_CREATED = "folder_created"
    FOLDER_UPDATED = "folder_updated"
    FOLDER_DELETED = "folder_deleted"

    # Task / Kanban events
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_MOVED = "task_moved"

    # Autonomous agent events (streamed while a task runs)
    AGENT_STEP = "agent_step"
    AGENT_LOG = "agent_log"

    # Subdomain-takeover scan progress (streamed while a scan runs)
    TAKEOVER_PROGRESS = "takeover_progress"
    TAKEOVER_DONE = "takeover_done"

    # System events
    SYSTEM_STATUS_CHANGED = "system_status_changed"
    ERROR = "error"


def create_event(event_type: EventType, data: Dict[str, Any], assessment_id: int = None) -> Dict[str, Any]:
    """
    Create a standardized event object

    Args:
        event_type: The type of event
        data: The event data payload
        assessment_id: Optional assessment ID this event relates to

    Returns:
        Formatted event dictionary
    """
    event = {
        "type": event_type.value,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }

    if assessment_id is not None:
        event["assessment_id"] = assessment_id

    return event


# Helper functions for common events

def event_assessment_created(assessment_data: dict) -> dict:
    """Create assessment_created event"""
    return create_event(
        EventType.ASSESSMENT_CREATED,
        {"assessment": assessment_data}
    )


def event_assessment_updated(assessment_id: int, updated_fields: dict) -> dict:
    """Create assessment_updated event"""
    return create_event(
        EventType.ASSESSMENT_UPDATED,
        {"assessment_id": assessment_id, "fields": updated_fields},
        assessment_id=assessment_id
    )


def event_assessment_deleted(assessment_id: int) -> dict:
    """Create assessment_deleted event"""
    return create_event(
        EventType.ASSESSMENT_DELETED,
        {"assessment_id": assessment_id}
    )


def event_card_added(assessment_id: int, card_data: dict) -> dict:
    """Create card_added event"""
    return create_event(
        EventType.CARD_ADDED,
        {"card": card_data},
        assessment_id=assessment_id
    )


def event_card_updated(assessment_id: int, card_id: int, card_data: dict) -> dict:
    """Create card_updated event"""
    return create_event(
        EventType.CARD_UPDATED,
        {"card_id": card_id, "card": card_data},
        assessment_id=assessment_id
    )


def event_card_deleted(assessment_id: int, card_id: int) -> dict:
    """Create card_deleted event"""
    return create_event(
        EventType.CARD_DELETED,
        {"card_id": card_id},
        assessment_id=assessment_id
    )


def event_asvs_updated(assessment_id: int, req_id: str, requirement_data: dict) -> dict:
    """Create asvs_updated event (a requirement verdict changed)"""
    return create_event(
        EventType.ASVS_UPDATED,
        {"req_id": req_id, "requirement": requirement_data},
        assessment_id=assessment_id
    )


def event_recon_added(assessment_id: int, recon_data: dict) -> dict:
    """Create recon_added event"""
    return create_event(
        EventType.RECON_ADDED,
        {"recon": recon_data},
        assessment_id=assessment_id
    )


def event_recon_updated(assessment_id: int, recon_id: int, recon_data: dict) -> dict:
    """Create recon_updated event"""
    return create_event(
        EventType.RECON_UPDATED,
        {"recon_id": recon_id, "recon": recon_data},
        assessment_id=assessment_id
    )


def event_recon_deleted(assessment_id: int, recon_id: int) -> dict:
    """Create recon_deleted event"""
    return create_event(
        EventType.RECON_DELETED,
        {"recon_id": recon_id},
        assessment_id=assessment_id
    )


def event_section_updated(assessment_id: int, section_data: dict) -> dict:
    """Create section_updated event"""
    return create_event(
        EventType.SECTION_UPDATED,
        {"section": section_data},
        assessment_id=assessment_id
    )


def event_command_completed(assessment_id: int, command_data: dict) -> dict:
    """Create command_completed event"""
    return create_event(
        EventType.COMMAND_COMPLETED,
        {"command": command_data},
        assessment_id=assessment_id
    )


def event_command_failed(assessment_id: int, command_data: dict) -> dict:
    """Create command_failed event"""
    return create_event(
        EventType.COMMAND_FAILED,
        {"command": command_data},
        assessment_id=assessment_id
    )


def event_credential_added(assessment_id: int, credential_data: dict) -> dict:
    """Create credential_added event"""
    return create_event(
        EventType.CREDENTIAL_ADDED,
        {"credential": credential_data},
        assessment_id=assessment_id
    )


def event_task_created(task_data: dict) -> dict:
    """Create task_created event (broadcast globally to the board)."""
    return create_event(EventType.TASK_CREATED, {"task": task_data})


def event_task_updated(task_id: int, task_data: dict) -> dict:
    """Create task_updated event."""
    return create_event(EventType.TASK_UPDATED, {"task_id": task_id, "task": task_data})


def event_task_deleted(task_id: int) -> dict:
    """Create task_deleted event."""
    return create_event(EventType.TASK_DELETED, {"task_id": task_id})


def event_task_moved(task_id: int, status: str, position: int) -> dict:
    """Create task_moved event (column/position change)."""
    return create_event(
        EventType.TASK_MOVED,
        {"task_id": task_id, "status": status, "position": position},
    )


def event_error(message: str, details: dict = None) -> dict:
    """Create error event"""
    data = {"message": message}
    if details:
        data["details"] = details
    return create_event(EventType.ERROR, data)
