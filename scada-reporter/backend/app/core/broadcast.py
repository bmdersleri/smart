import logging

from fastapi import WebSocket

from app.core import metrics

logger = logging.getLogger(__name__)


class ConnectionManager:
    """In-memory WebSocket connection manager for live data broadcasting."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        metrics.active_websockets.inc()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            metrics.active_websockets.dec()

    async def broadcast(self, message: dict):
        """Broadcasts a JSON message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("WebSocket broadcast error: %s", e)
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


# Global singleton instance for the single-node setup
broadcast_manager = ConnectionManager()
