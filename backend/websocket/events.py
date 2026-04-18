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

    # Agent run events (UI-initiated Claude sessions)
    AGENT_RUN_STARTED = "agent_run_started"
    AGENT_RUN_MESSAGE = "agent_run_message"
    AGENT_RUN_COMPLETED = "agent_run_completed"
    AGENT_RUN_FAILED = "agent_run_failed"
    AGENT_RUN_STOPPED = "agent_run_stopped"

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


def event_agent_run_started(assessment_id: int, run_data: dict) -> dict:
    """Create agent_run_started event"""
    return create_event(
        EventType.AGENT_RUN_STARTED,
        {"run": run_data},
        assessment_id=assessment_id,
    )


def event_agent_run_message(assessment_id: int, run_id: int, message: dict) -> dict:
    """Create agent_run_message event — one SDK-level event in the stream"""
    return create_event(
        EventType.AGENT_RUN_MESSAGE,
        {"run_id": run_id, "message": message},
        assessment_id=assessment_id,
    )


def event_agent_run_completed(assessment_id: int, run_data: dict) -> dict:
    """Create agent_run_completed event"""
    return create_event(
        EventType.AGENT_RUN_COMPLETED,
        {"run": run_data},
        assessment_id=assessment_id,
    )


def event_agent_run_failed(assessment_id: int, run_id: int, error: str) -> dict:
    """Create agent_run_failed event"""
    return create_event(
        EventType.AGENT_RUN_FAILED,
        {"run_id": run_id, "error": error},
        assessment_id=assessment_id,
    )


def event_agent_run_stopped(assessment_id: int, run_id: int) -> dict:
    """Create agent_run_stopped event"""
    return create_event(
        EventType.AGENT_RUN_STOPPED,
        {"run_id": run_id},
        assessment_id=assessment_id,
    )


def event_error(message: str, details: dict = None) -> dict:
    """Create error event"""
    data = {"message": message}
    if details:
        data["details"] = details
    return create_event(EventType.ERROR, data)
