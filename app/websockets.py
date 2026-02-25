from fastapi import WebSocket
from typing import Dict, List, Set
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # user_id -> Dict[websocket, status_string]
        self.active_connections: Dict[int, Dict[WebSocket, str]] = {}
        # user_id -> currently broadcasted aggregated status
        self.user_statuses: Dict[int, str] = {}

    def _get_aggregated_status(self, user_id: int) -> str:
        if user_id not in self.active_connections or not self.active_connections[user_id]:
            return "offline"
        
        statuses = self.active_connections[user_id].values()
        if "online" in statuses:
            return "online"
        return "away"

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = {}
        
        # New connection defaults to online
        self.active_connections[user_id][websocket] = "online"
        
        new_agg_status = self._get_aggregated_status(user_id)
        old_agg_status = self.user_statuses.get(user_id, "offline")
        
        self.user_statuses[user_id] = new_agg_status
        
        logger.info(f"User {user_id} connected. Total connections for user: {len(self.active_connections[user_id])}")
        
        if new_agg_status != old_agg_status:
            await self.broadcast_status(user_id, new_agg_status)

    async def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                del self.active_connections[user_id][websocket]
            
            logger.info(f"User {user_id} disconnected. Remaining connections: {len(self.active_connections[user_id])}")
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                if user_id in self.user_statuses:
                    del self.user_statuses[user_id]
                await self.broadcast_status(user_id, "offline")
            else:
                new_agg_status = self._get_aggregated_status(user_id)
                old_agg_status = self.user_statuses.get(user_id)
                if new_agg_status != old_agg_status:
                    self.user_statuses[user_id] = new_agg_status
                    await self.broadcast_status(user_id, new_agg_status)

    async def update_user_status(self, user_id: int, status: str, websocket: WebSocket):
        if user_id in self.active_connections and websocket in self.active_connections[user_id]:
            if status in ["online", "away"]:
                self.active_connections[user_id][websocket] = status
                
                new_agg_status = self._get_aggregated_status(user_id)
                old_agg_status = self.user_statuses.get(user_id)
                
                if new_agg_status != old_agg_status:
                    self.user_statuses[user_id] = new_agg_status
                    await self.broadcast_status(user_id, new_agg_status)

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
            # Create a copy of sockets to avoid dict mutation during iteration
            sockets = list(self.active_connections[user_id].keys())
            dead_sockets = []
            for connection in sockets:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send message to user {user_id}: {str(e)}")
                    dead_sockets.append(connection)
            
            for connection in dead_sockets:
                if user_id in self.active_connections and connection in self.active_connections[user_id]:
                    del self.active_connections[user_id][connection]
            
            if user_id in self.active_connections and not self.active_connections[user_id]:
                del self.active_connections[user_id]
                if user_id in self.user_statuses:
                    del self.user_statuses[user_id]
                
                # IMPORTANT: we don't broadcast offline status here to prevent recursion
                # if other users' sockets are also dead. The offline status will be organically
                # calculated or broadcasted by explicit disconnects instead.

    async def broadcast_to_chat(self, message: dict, member_ids: List[int]):
        logger.info(f"ConnectionManager: Broadcasting to members {member_ids}")
        for user_id in member_ids:
            await self.send_personal_message(message, user_id)

    async def handle_message(self, user_id: int, msg: dict, websocket: WebSocket):
        msg_type = msg.get("type")
        if msg_type == "typing":
            chat_id = msg.get("chat_id")
            is_typing = msg.get("is_typing", False)
            if chat_id:
                try:
                    from .services.chat_service import get_chat_member_ids
                    from .models import User as DBUser
                    from sqlalchemy import select
                    from .database import AsyncSessionLocal
                    async with AsyncSessionLocal() as db:
                        member_ids_task = await get_chat_member_ids(db, chat_id)
                        user_name_stmt = select(DBUser.username).where(DBUser.id == user_id)
                        user_name_result = await db.execute(user_name_stmt)
                        user_name = user_name_result.scalar()
                        member_ids = member_ids_task

                        if user_name:
                            ws_msg = {
                                "type": "typing",
                                "data": {
                                    "chat_id": chat_id,
                                    "user_id": user_id,
                                    "username": user_name,
                                    "is_typing": is_typing
                                }
                            }
                            recipients = [m_id for m_id in member_ids if m_id != user_id]
                            await self.broadcast_to_chat(ws_msg, recipients)
                except Exception as e:
                    logger.error(f"Typing broadcast failure: {e}")
        
        elif msg_type == "user_status_update":
            new_status = msg.get("status")
            if new_status:
                await self.update_user_status(user_id, new_status, websocket)

manager = ConnectionManager()
