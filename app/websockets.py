from fastapi import WebSocket
from typing import Dict, List, Set
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # user_id -> list of active websockets
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        is_new_online = user_id not in self.active_connections
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(f"User {user_id} connected. Total connections for user: {len(self.active_connections[user_id])}")
        
        # If this is the first connection for this user, notify others
        if is_new_online:
            await self.broadcast_status(user_id, True)

    async def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            logger.info(f"User {user_id} disconnected. Remaining connections: {len(self.active_connections.get(user_id, []))}")
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Last connection closed, notify others
                await self.broadcast_status(user_id, False)

    async def broadcast_status(self, user_id: int, is_online: bool):
        status_msg = {
            "type": "user_status",
            "data": {
                "user_id": user_id,
                "online": is_online
            }
        }
        # Broadcast to EVERYONE for simplicity in this MVP, 
        # or we could optimize to only broadcast to "friends/contacts"
        for other_user_id in self.active_connections:
            if other_user_id != user_id:
                await self.send_personal_message(status_msg, other_user_id)

    def get_online_users(self) -> List[int]:
        return list(self.active_connections.keys())

    async def send_personal_message(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send message to user {user_id}: {str(e)}")
                    dead_connections.add(connection)
            
            # Clean up dead connections
            for dead in dead_connections:
                self.active_connections[user_id].remove(dead)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast_to_chat(self, message: dict, member_ids: List[int]):
        logger.info(f"ConnectionManager: Broadcasting to members {member_ids}")
        for user_id in member_ids:
            await self.send_personal_message(message, user_id)

manager = ConnectionManager()
