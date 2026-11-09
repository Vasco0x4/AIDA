"""
WebSocket API endpoints for real-time communication
"""
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from auth import decode_token
from database import SessionLocal
from models.user import User
from websocket.manager import manager
from websocket.events import EventType, create_event
from utils.logger import get_logger
import json

logger = get_logger(__name__)

router = APIRouter()


def _authenticate_ws(token: Optional[str]) -> Optional[User]:
    """Validate a JWT token from a WebSocket query string. Returns the User
    or None if the token is missing/invalid/inactive.
    """
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if user and user.is_active:
            return user
        return None
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_global(websocket: WebSocket, token: Optional[str] = None):
    """Global WebSocket endpoint - receives all events."""
    user = _authenticate_ws(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        await manager.connect(websocket)

        # Send connection confirmation (with error handling)
        try:
            await manager.send_personal(
                websocket,
                create_event(EventType.CONNECTED, {"message": "Connected to global events"})
            )
            logger.info("Client connected to global WebSocket")
        except Exception:
            # Connection closed before we could send - this is fine
            logger.debug("Could not send connection message (client disconnected early)")
            manager.disconnect(websocket)
            return

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                message_type = message.get("type")

                # Handle ping/pong for connection health
                if message_type == "ping":
                    await manager.send_personal(
                        websocket,
                        create_event(EventType.PONG, {"message": "pong"})
                    )
                    logger.debug("Responded to ping")

                else:
                    logger.warning(
                        "Unknown WebSocket message type",
                        message_type=message_type
                    )

            except json.JSONDecodeError:
                logger.error("Invalid JSON received from WebSocket client")
                await manager.send_personal(
                    websocket,
                    create_event(
                        EventType.ERROR,
                        {"message": "Invalid JSON format"}
                    )
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from global WebSocket")

    except Exception as e:
        logger.error("WebSocket error", error=str(e), exc_info=True)
        manager.disconnect(websocket)


@router.websocket("/ws/assessment/{assessment_id}")
async def websocket_assessment(
    websocket: WebSocket,
    assessment_id: int,
    token: Optional[str] = None,
):
    """Assessment-specific WebSocket endpoint - only receives events for a given assessment."""
    user = _authenticate_ws(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        await manager.connect(websocket, assessment_id=assessment_id)

        # Send connection confirmation (with error handling)
        try:
            await manager.send_personal(
                websocket,
                create_event(
                    EventType.CONNECTED,
                    {
                        "message": f"Connected to assessment {assessment_id} events",
                        "assessment_id": assessment_id
                    },
                    assessment_id=assessment_id
                )
            )
            logger.info(
                "Client connected to assessment WebSocket",
                assessment_id=assessment_id
            )
        except Exception:
            # Connection closed before we could send - this is fine
            logger.debug(
                "Could not send connection message (client disconnected early)",
                assessment_id=assessment_id
            )
            manager.disconnect(websocket)
            return

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                message_type = message.get("type")

                # Handle ping/pong for connection health
                if message_type == "ping":
                    await manager.send_personal(
                        websocket,
                        create_event(EventType.PONG, {"message": "pong"})
                    )
                    logger.debug("Responded to ping", assessment_id=assessment_id)

                else:
                    logger.warning(
                        "Unknown WebSocket message type",
                        message_type=message_type,
                        assessment_id=assessment_id
                    )

            except json.JSONDecodeError:
                logger.error(
                    "Invalid JSON received from WebSocket client",
                    assessment_id=assessment_id
                )
                await manager.send_personal(
                    websocket,
                    create_event(
                        EventType.ERROR,
                        {"message": "Invalid JSON format"}
                    )
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(
            "Client disconnected from assessment WebSocket",
            assessment_id=assessment_id
        )

    except Exception as e:
        logger.error(
            "WebSocket error",
            error=str(e),
            assessment_id=assessment_id,
            exc_info=True
        )
        manager.disconnect(websocket)
