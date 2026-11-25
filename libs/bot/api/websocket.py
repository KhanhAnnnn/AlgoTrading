"""
libs/bot/api/websocket.py — WebSocket Streaming & Real-Time Sync (GĐ35)
Implements /ws/v2/bots/{session_id} with sequence IDs, heartbeats, deduplication,
and snapshot resynchronization for AlgoTrading V2.0.
"""

from typing import Dict, List, Set, Any, Optional
from datetime import datetime, timezone
import json
import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("v2-websocket")


class BotWebSocketManager:
    """
    Manages active WebSocket connections per bot session and global subscribers.
    Maintains bounded event history, monotonic sequence numbers, and resynchronization.
    """

    def __init__(self, history_limit: int = 200):
        # session_id -> Set[WebSocket]
        self._session_connections: Dict[str, Set[WebSocket]] = {}
        # Global connections listening to all bots
        self._global_connections: Set[WebSocket] = set()

        # session_id -> current sequence number
        self._sequence_counters: Dict[str, int] = {}
        # session_id -> List[Dict[str, Any]] (bounded buffer)
        self._event_buffers: Dict[str, List[Dict[str, Any]]] = {}
        self.history_limit = history_limit
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def buffer_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Buffers an event for a bot session."""
        buf = self._event_buffers.setdefault(session_id, [])
        buf.append(event)
        if len(buf) > self.history_limit:
            self._event_buffers[session_id] = buf[-self.history_limit:]

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None):
        """Accepts and registers a new WebSocket client."""
        self._main_loop = asyncio.get_running_loop()
        await websocket.accept()
        if session_id:
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._sequence_counters.setdefault(session_id, 0)
            self._event_buffers.setdefault(session_id, [])
            self._session_connections[session_id].add(websocket)
            logger.info(f"WebSocket client connected to session '{session_id}' (total: {len(self._session_connections[session_id])})")
        else:
            self._global_connections.add(websocket)
            logger.info(f"WebSocket client connected to global stream (total: {len(self._global_connections)})")

    def disconnect(self, websocket: WebSocket, session_id: Optional[str] = None):
        """Unregisters a disconnected WebSocket client."""
        if session_id and session_id in self._session_connections:
            self._session_connections[session_id].discard(websocket)
            if not self._session_connections[session_id]:
                # Keep buffer and counter for reconnection resync
                pass
            logger.info(f"WebSocket client disconnected from session '{session_id}'")
        else:
            self._global_connections.discard(websocket)
            logger.info("WebSocket client disconnected from global stream")

    def _next_seq_id(self, session_id: str) -> int:
        """Returns the next monotonically increasing sequence ID for this session."""
        val = self._sequence_counters.get(session_id, 0) + 1
        self._sequence_counters[session_id] = val
        return val

    async def broadcast_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Assigns sequence ID, stores in buffer, and broadcasts message to subscribers.
        """
        seq_id = self._next_seq_id(session_id)
        msg = {
            "seq_id": seq_id,
            "session_id": session_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "environment": "SIMULATION",
        }

        # Store in bounded replay buffer
        buf = self._event_buffers.setdefault(session_id, [])
        buf.append(msg)
        if len(buf) > self.history_limit:
            buf.pop(0)

        # Broadcast to session-specific connections
        targets: List[WebSocket] = list(self._session_connections.get(session_id, set()))
        # Also broadcast to global connections
        targets.extend(list(self._global_connections))

        dead_sockets: List[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(msg)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message to client: {e}")
                dead_sockets.append(ws)

        for ws in dead_sockets:
            self.disconnect(ws, session_id)

        return msg

    def broadcast_sync(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Synchronously dispatches broadcast message across active client connections,
        scheduling on the main event loop thread-safely.
        """
        if self._main_loop and self._main_loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.broadcast_event(session_id, event_type, payload),
                    self._main_loop,
                )
                return future.result(timeout=2.0)
            except Exception as e:
                logger.warning(f"broadcast_sync error: {e}")

        # Fallback local dispatch for buffer tracking
        seq_id = self._next_seq_id(session_id)
        msg = {
            "seq_id": seq_id,
            "session_id": session_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "environment": "SIMULATION",
        }
        buf = self._event_buffers.setdefault(session_id, [])
        buf.append(msg)
        if len(buf) > self.history_limit:
            buf.pop(0)
        return msg

    async def send_snapshot(self, websocket: WebSocket, session_id: str, snapshot_payload: Dict[str, Any]):
        """Sends a complete current state snapshot to a newly connected or resyncing client."""
        seq_id = self._sequence_counters.get(session_id, 0)
        msg = {
            "seq_id": seq_id,
            "session_id": session_id,
            "event_type": "SNAPSHOT",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": snapshot_payload,
            "environment": "SIMULATION",
        }
        try:
            await websocket.send_json(msg)
        except Exception as e:
            logger.error(f"Failed to send snapshot to client: {e}")

    async def resynchronize(
        self,
        websocket: WebSocket,
        session_id: str,
        last_seq_id: int,
        fallback_snapshot_fn: Optional[Any] = None,
    ):
        """
        Replays missed events from last_seq_id.
        If last_seq_id is too old or buffer cannot satisfy it, dispatches full SNAPSHOT.
        """
        buf = self._event_buffers.get(session_id, [])
        if not buf:
            if fallback_snapshot_fn:
                snap = fallback_snapshot_fn(session_id)
                await self.send_snapshot(websocket, session_id, snap)
            return

        min_seq = buf[0]["seq_id"]
        if last_seq_id < min_seq - 1:
            # Client missed too many events: fallback to full snapshot
            logger.info(f"Client last_seq_id={last_seq_id} is behind buffer start={min_seq}. Dispatching full SNAPSHOT.")
            if fallback_snapshot_fn:
                snap = fallback_snapshot_fn(session_id)
                await self.send_snapshot(websocket, session_id, snap)
            return

        # Replay missed events
        missed = [e for e in buf if e["seq_id"] > last_seq_id]
        logger.info(f"Replaying {len(missed)} missed events to client (last_seq_id={last_seq_id})")
        for m in missed:
            try:
                await websocket.send_json(m)
            except Exception:
                break


# Global singleton instance
ws_manager = BotWebSocketManager()
