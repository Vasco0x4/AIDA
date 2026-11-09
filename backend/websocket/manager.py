"""
WebSocket Connection Manager
Handles WebSocket connections and event broadcasting
"""
from typing import Dict, List, Set
from fastapi import WebSocket
from utils.logger import get_logger
import json

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events"""

    def __init__(self):
        # All active connections
        self.active_connections: List[WebSocket] = []

        # Global connections (no assessment_id) — receive all events
        self.global_connections: Set[WebSocket] = set()

        # Connections grouped by assessment_id for targeted broadcasting
        self.assessment_connections: Dict[int, Set[WebSocket]] = {}

        logger.info("WebSocket ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, assessment_id: int = None):
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: The WebSocket connection
            assessment_id: Optional assessment ID to subscribe to specific events
        """
        await websocket.accept()
        self.active_connections.append(websocket)

        # Subscribe to assessment-specific events if provided
        if assessment_id is not None:
            if assessment_id not in self.assessment_connections:
                self.assessment_connections[assessment_id] = set()
            self.assessment_connections[assessment_id].add(websocket)

            logger.info(
                "WebSocket connected",
                assessment_id=assessment_id,
                total_connections=len(self.active_connections),
                assessment_connections=len(self.assessment_connections[assessment_id])
            )
        else:
            self.global_connections.add(websocket)
            logger.info(
                "WebSocket connected (global)",
                total_connections=len(self.active_connections)
            )

    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection

        Args:
            websocket: The WebSocket connection to remove
        """
        # Remove from active connections
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Remove from global connections
        self.global_connections.discard(websocket)

        # Remove from assessment-specific connections. Iterate over a copy so we
        # can delete now-empty sets in place (they previously leaked forever).
        for assessment_id, connections in list(self.assessment_connections.items()):
            if websocket in connections:
                connections.remove(websocket)
                if not connections:
                    del self.assessment_connections[assessment_id]
                logger.info(
                    "WebSocket disconnected",
                    assessment_id=assessment_id,
                    remaining_connections=len(connections)
                )

        logger.info(
            "WebSocket disconnected",
            total_connections=len(self.active_connections)
        )

    async def broadcast(self, event: dict, assessment_id: int = None):
        """
        Broadcast an event to all or specific connections

        Args:
            event: The event data to broadcast (must be JSON serializable)
            assessment_id: If provided, only broadcast to connections subscribed to this assessment
        """
        # Serialize event to JSON
        message = json.dumps(event)

        # Determine target connections
        if assessment_id is not None:
            # Broadcast to assessment-specific connections + global connections
            # Global connections (e.g. /commands page) must receive all events
            target_connections = self.assessment_connections.get(assessment_id, set()) | self.global_connections
            logger.debug(
                "Broadcasting to assessment",
                event_type=event.get("type"),
                assessment_id=assessment_id,
                target_connections=len(target_connections)
            )
        else:
            # Broadcast to all connections (snapshot: disconnect() mutates the
            # list during cleanup below)
            target_connections = list(self.active_connections)
            logger.debug(
                "Broadcasting globally",
                event_type=event.get("type"),
                target_connections=len(target_connections)
            )

        # Send to all target connections
        disconnected = []
        for connection in target_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(
                    "Failed to send WebSocket message",
                    error=str(e),
                    event_type=event.get("type")
                )
                disconnected.append(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection)

    async def send_personal(self, websocket: WebSocket, event: dict):
        """
        Send an event to a specific WebSocket connection

        Args:
            websocket: The target WebSocket connection
            event: The event data to send
        """
        try:
            message = json.dumps(event)
            await websocket.send_text(message)
            logger.debug(
                "Sent personal message",
                event_type=event.get("type")
            )
        except RuntimeError:
            # Connection already closed - this is normal behavior
            logger.debug(
                "Could not send personal message (connection closed)",
                event_type=event.get("type")
            )
            self.disconnect(websocket)
        except Exception as e:
            # Unexpected error
            logger.error(
                "Failed to send personal WebSocket message",
                error=str(e),
                event_type=event.get("type")
            )
            self.disconnect(websocket)

    def get_connection_count(self, assessment_id: int = None) -> int:
        """
        Get the number of active connections

        Args:
            assessment_id: If provided, return count for this assessment only

        Returns:
            Number of active connections
        """
        if assessment_id is not None:
            return len(self.assessment_connections.get(assessment_id, set()))
        return len(self.active_connections)


# Global connection manager instance
manager = ConnectionManager()
