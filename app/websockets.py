from fastapi import WebSocket
from typing import Dict, List, Set
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # user_id -> list of active websockets
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # user_id -> status string (online, away)
        self.user_statuses: Dict[int, str] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        is_new_online = user_id not in self.active_connections
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
            self.user_statuses[user_id] = "online"
        self.active_connections[user_id].add(websocket)
        logger.info(f"User {user_id} connected. Total connections for user: {len(self.active_connections[user_id])}")
        
        # If this is the first connection for this user, notify others
        if is_new_online:
            await self.broadcast_status(user_id, "online")

    async def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            logger.info(f"User {user_id} disconnected. Remaining connections: {len(self.active_connections.get(user_id, []))}")
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                if user_id in self.user_statuses:
                    del self.user_statuses[user_id]
                # Last connection closed, notify others
                await self.broadcast_status(user_id, "offline")

    async def update_user_status(self, user_id: int, status: str):
        if user_id in self.active_connections:
            # Valid statuses: online, away
            if status in ["online", "away"]:
                self.user_statuses[user_id] = status
                await self.broadcast_status(user_id, status)

    async def broadcast_status(self, user_id: int, status: str):
        status_msg = {
            "type": "user_status",
            "data": {
                "user_id": user_id,
                "status": status,
                "online": status != "offline"
            }
        }
        # In a real app, only broadcast to contacts/members of mutual chats
        # For simplicity, we broadcast to all current online users
        for other_user_id in list(self.active_connections.keys()):
            if other_user_id != user_id:
                await self.send_personal_message(status_msg, other_user_id)

    async def broadcast_user_update(self, user_id: int, username: str, avatar_path: str = None):
        update_msg = {
            "type": "user_updated",
            "data": {
                "id": user_id,
                "username": username,
                "avatar_path": avatar_path
            }
        }
        for other_user_id in list(self.active_connections.keys()):
            await self.send_personal_message(update_msg, other_user_id)

    def get_online_users(self) -> Dict[int, str]:
        return self.user_statuses

    async def send_personal_message(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            sockets = list(self.active_connections[user_id])
            for connection in sockets:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send message to user {user_id}: {str(e)}")
                    if user_id in self.active_connections:
                        self.active_connections[user_id].discard(connection)
            
            if user_id in self.active_connections and not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # If the last socket just died, notify others
                await self.broadcast_status(user_id, False)

    async def broadcast_to_chat(self, message: dict, member_ids: List[int]):
        logger.info(f"ConnectionManager: Broadcasting to members {member_ids}")
        for user_id in member_ids:
            await self.send_personal_message(message, user_id)

manager = ConnectionManager()
