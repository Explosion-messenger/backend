from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional
import asyncio
import os
import logging
from datetime import datetime, timedelta, timezone
from ..models import Message, ChatMember, User, File, MessageRead
from ..schemas import MessageCreate
from ..websockets import manager

logger = logging.getLogger(__name__)

async def get_messages(db: AsyncSession, chat_id: int, user_id: int, offset: int = 0, limit: int = 50) -> List[Message]:
    # Verify user is in chat
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None

    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(
            joinedload(Message.file), 
            joinedload(Message.sender),
            selectinload(Message.read_by),
            selectinload(Message.reactions)
        )
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.unique().scalars().all()

async def mark_as_read(db: AsyncSession, message_id: int, user_id: int):
    # Verify message exists and user has access to it
    stmt = (
        select(Message)
        .join(ChatMember, ChatMember.chat_id == Message.chat_id)
        .where(Message.id == message_id, ChatMember.user_id == user_id)
    )
    res = await db.execute(stmt)
    message = res.scalars().first()
    if not message:
        return False

    # Don't mark own messages as read (or maybe we do? standard is usually don't need to)
    if message.sender_id == user_id:
        return True

    # Check if already read
    stmt = select(MessageRead).where(MessageRead.message_id == message_id, MessageRead.user_id == user_id)
    res = await db.execute(stmt)
    if res.scalars().first():
        return True

    # Mark as read
    db_read = MessageRead(message_id=message_id, user_id=user_id)
    db.add(db_read)
    await db.commit()
    
    # Prepare broadcast
    read_at = datetime.now(timezone.utc).isoformat()
    stmt = select(ChatMember.user_id).where(ChatMember.chat_id == message.chat_id)
    res = await db.execute(stmt)
    member_ids = list(res.scalars().all())

    ws_msg = {
        "type": "message_read",
        "data": {
            "message_id": message_id,
            "chat_id": message.chat_id,
            "user_id": user_id,
            "read_at": read_at
        }
    }
    
    await manager.broadcast_to_chat(ws_msg, member_ids)
    return True

async def mark_all_as_read(db: AsyncSession, chat_id: int, user_id: int):
    # Verify user is in chat
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    res = await db.execute(stmt)
    if not res.scalars().first():
        return False

    # Find unread messages for this user in this chat
    from sqlalchemy import and_, not_
    unread_stmt = (
        select(Message.id)
        .where(
            Message.chat_id == chat_id,
            Message.sender_id != user_id
        )
        .where(
            not_(
                select(MessageRead.id)
                .where(MessageRead.message_id == Message.id, MessageRead.user_id == user_id)
                .exists()
            )
        )
    )
    unread_ids = (await db.execute(unread_stmt)).scalars().all()
    
    if not unread_ids:
        return True

    # Mark all as read
    for msg_id in unread_ids:
        db.add(MessageRead(message_id=msg_id, user_id=user_id))
    
    await db.commit()

    # Notify members via WS for each read message
    # To avoid flood, we could send a single bulk_read event, 
    # but the current frontend expects message_read.
    # We'll batch them and send.
    read_at = datetime.now(timezone.utc).isoformat()
    stmt = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
    member_ids = list((await db.execute(stmt)).scalars().all())

    for msg_id in unread_ids:
        ws_msg = {
            "type": "message_read",
            "data": {
                "message_id": msg_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "read_at": read_at
            }
        }
        await manager.broadcast_to_chat(ws_msg, member_ids)

    return True

async def send_message(db: AsyncSession, payload: MessageCreate, sender_id: int) -> Message:
    # 1. Artificial delay to ensure serialization and meet user request for business logic delay
    await asyncio.sleep(0.1)

    # 2. Verify user is in chat
    stmt = select(ChatMember).where(ChatMember.chat_id == payload.chat_id, ChatMember.user_id == sender_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None

    # 3. Deduplication: Check if the exact same message was sent by the same user in the last 1 second
    if payload.text:
        one_second_ago = datetime.now(timezone.utc) - timedelta(seconds=1)
        dup_stmt = (
            select(Message)
            .where(
                Message.chat_id == payload.chat_id,
                Message.sender_id == sender_id,
                Message.text == payload.text,
                Message.created_at >= one_second_ago
            )
            .order_by(Message.created_at.desc())
        )
        dup_result = await db.execute(dup_stmt)
        existing_msg = dup_result.scalars().first()
        if existing_msg:
            # Already sent, return the existing one to avoid duplicates
            # We still refetch with eager loading to be safe
            stmt = select(Message).where(Message.id == existing_msg.id).options(joinedload(Message.file), joinedload(Message.sender))
            return (await db.execute(stmt)).scalars().first()

    # 4. Create new message
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
        .options(
            joinedload(Message.file), 
            joinedload(Message.sender),
            selectinload(Message.read_by),
            selectinload(Message.reactions)
        )
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
            "created_at": message.created_at.isoformat(),
            "read_by": [],
            "reactions": []
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

async def delete_messages(db: AsyncSession, message_ids: List[int], user_id: int) -> bool:
    stmt = (
        select(Message)
        .where(Message.id.in_(message_ids), Message.sender_id == user_id)
        .options(joinedload(Message.file))
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    if not messages:
        return False
    
    chat_id_to_members = {}
    
    for message in messages:
        cid = message.chat_id
        if cid not in chat_id_to_members:
            stmt = select(ChatMember.user_id).where(ChatMember.chat_id == cid)
            chat_id_to_members[cid] = (await db.execute(stmt)).scalars().all()
            
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
    
    # Broadcast deletions
    for message in messages:
        ws_msg = {
            "type": "delete_message",
            "data": {
                "message_id": message.id,
                "chat_id": message.chat_id
            }
        }
        await manager.broadcast_to_chat(ws_msg, list(chat_id_to_members[message.chat_id]))
        
    return True
