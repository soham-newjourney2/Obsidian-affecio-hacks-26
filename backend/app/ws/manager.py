"""In-process registry of room sockets. Only verified members are ever registered, so a room
broadcast reaches members only. Single process (one uvicorn worker), like the rate limiters."""

import contextlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocket

from backend.app.core.security import TokenClaims

log = logging.getLogger("echo.ws")


@dataclass(eq=False)
class Connection:
    ws: WebSocket
    room_id: uuid.UUID
    member_id: uuid.UUID
    user_id: uuid.UUID
    claims: TokenClaims
    open: bool = field(default=True)


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: defaultdict[uuid.UUID, set[Connection]] = defaultdict(set)

    def add(self, conn: Connection) -> bool:
        """Registers a socket. Returns True if the member just came online (no other tab)."""
        came_online = conn.member_id not in self.online_members(conn.room_id)
        self._rooms[conn.room_id].add(conn)
        return came_online

    def remove(self, conn: Connection) -> bool:
        """Unregisters a socket. Returns True if the member is now offline (no other tab)."""
        conn.open = False
        room = self._rooms.get(conn.room_id)
        if room is not None:
            room.discard(conn)
            if not room:
                del self._rooms[conn.room_id]
        return conn.member_id not in self.online_members(conn.room_id)

    def connections(self, room_id: uuid.UUID) -> list[Connection]:
        return [c for c in self._rooms.get(room_id, ()) if c.open]

    def online_members(self, room_id: uuid.UUID) -> set[uuid.UUID]:
        return {c.member_id for c in self.connections(room_id)}

    async def send(self, conn: Connection, message: dict[str, Any]) -> bool:
        if not conn.open:
            return False
        try:
            await conn.ws.send_json(message)
            return True
        except Exception:  # peer vanished mid-send; the receive loop cleans up
            conn.open = False
            log.info("ws send failed room=%s", conn.room_id)
            return False

    async def broadcast(self, room_id: uuid.UUID, message: dict[str, Any]) -> None:
        for conn in self.connections(room_id):
            await self.send(conn, message)

    async def close_member(self, room_id: uuid.UUID, member_id: uuid.UUID, code: int) -> None:
        for conn in self.connections(room_id):
            if conn.member_id == member_id:
                conn.open = False
                with contextlib.suppress(Exception):
                    await conn.ws.close(code)
