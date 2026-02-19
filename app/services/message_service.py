from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from typing import List, Optional
import os
import logging
from ..models import Message, ChatMember, User, File
from ..schemas import MessageCreate
from ..websockets import manager

logger = logging.getLogger(__name__)

async def get_messages(db: AsyncSession, chat_id: int, user_id: int, offset: int = 0, limit: int = 50) -> List[Message]:
    # Verify user is in chat
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None  # Or raise exception, but service can return None and router raises 403

    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(joinedload(Message.file), joinedload(Message.sender))
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def send_message(db: AsyncSession, payload: MessageCreate, sender_id: int) -> Message:
    # Verify user is in chat
    stmt = select(ChatMember).where(ChatMember.chat_id == payload.chat_id, ChatMember.user_id == sender_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None

    message = Message(
        chat_id=payload.chat_id,
        sender_id=sender_id,
        text=payload.text,
        file_id=payload.file_id
    )
    db.add(message)
    await db.commit()
    
    # Refetch with eager loading
    stmt = (
        select(Message)
        .where(Message.id == message.id)
        .options(joinedload(Message.file), joinedload(Message.sender))
    )
    result = await db.execute(stmt)
    message = result.scalars().first()
    
    # Notify via WebSocket
    stmt = select(ChatMember.user_id).where(ChatMember.chat_id == payload.chat_id)
    member_ids = (await db.execute(stmt)).scalars().all()
    
    ws_msg = {
        "type": "new_message",
        "data": {
            "id": message.id,
            "chat_id": message.chat_id,
            "sender_id": message.sender_id,
            "sender": {
                "id": message.sender.id,
                "username": message.sender.username,
                "avatar_path": message.sender.avatar_path
            },
            "text": message.text,
            "file": {
                "id": message.file.id,
                "filename": message.file.filename,
                "path": message.file.path,
                "mime_type": message.file.mime_type,
                "size": message.file.size
            } if message.file else None,
            "created_at": message.created_at.isoformat()
        }
    }
    await manager.broadcast_to_chat(ws_msg, list(member_ids))
    
    return message

async def delete_message(db: AsyncSession, message_id: int, user_id: int) -> bool:
    stmt = (
        select(Message)
        .where(Message.id == message_id)
        .options(joinedload(Message.file))
    )
    result = await db.execute(stmt)
    message = result.scalars().first()
    
    if not message or message.sender_id != user_id:
        return False
    
    chat_id = message.chat_id
    stmt = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
    member_ids = (await db.execute(stmt)).scalars().all()
    
    if message.file:
        file_path = os.path.join("uploads", message.file.path)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Failed to delete file {file_path}: {e}")
        await db.delete(message.file)

    await db.delete(message)
    await db.commit()
    
    ws_msg = {
        "type": "delete_message",
        "data": {
            "message_id": message_id,
            "chat_id": chat_id
        }
    }
    await manager.broadcast_to_chat(ws_msg, list(member_ids))
    return True
