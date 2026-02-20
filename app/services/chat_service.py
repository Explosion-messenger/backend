from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional
import os
import shutil
from ..config import settings
from ..models import Chat, ChatMember, User, Message
from ..schemas import ChatCreate, ChatOut
from ..websockets import manager

async def get_user_chats(db: AsyncSession, user_id: int) -> List[ChatOut]:
    # Subquery: get the latest message ID for each chat
    from sqlalchemy import func
    last_msg_subq = (
        select(func.max(Message.id).label("max_id"))
        .where(Message.chat_id == Chat.id)
        .correlate(Chat)
        .scalar_subquery()
    )

    stmt = (
        select(Chat)
        .join(ChatMember)
        .where(ChatMember.user_id == user_id)
        .options(
            selectinload(Chat.members).joinedload(ChatMember.user),
        )
    )
    result = await db.execute(stmt)
    chats = result.unique().scalars().all()
    
    # Fetch last messages for all chats in a single query
    chat_ids = [chat.id for chat in chats]
    last_messages: dict[int, Message] = {}
    if chat_ids:
        last_msg_ids_stmt = (
            select(func.max(Message.id).label("msg_id"), Message.chat_id)
            .where(Message.chat_id.in_(chat_ids))
            .group_by(Message.chat_id)
        )
        last_msg_ids_result = await db.execute(last_msg_ids_stmt)
        msg_id_map = {row.chat_id: row.msg_id for row in last_msg_ids_result}
        
        if msg_id_map:
            msgs_stmt = (
                select(Message)
                .where(Message.id.in_(msg_id_map.values()))
                .options(
                    joinedload(Message.sender), 
                    joinedload(Message.file),
                    selectinload(Message.read_by),
                    selectinload(Message.reactions)
                )
            )
            msgs_result = await db.execute(msgs_stmt)
            for msg in msgs_result.unique().scalars().all():
                last_messages[msg.chat_id] = msg

    out = []
    for chat in chats:
        members = [cm.user for cm in chat.members]
        last_msg = last_messages.get(chat.id)
        
        out.append(ChatOut(
            id=chat.id,
            name=chat.name,
            avatar_path=chat.avatar_path,
            is_group=chat.is_group,
            created_at=chat.created_at,
            members=members,
            last_message=last_msg
        ))
    return out

async def create_chat(db: AsyncSession, payload: ChatCreate, creator_id: int) -> Optional[ChatOut]:
    chat_id = None
    
    if payload.is_group:
        if not payload.member_ids:
            return None
        
        new_chat = Chat(name=payload.name, is_group=True)
        db.add(new_chat)
        await db.flush()
        chat_id = new_chat.id
        
        member_ids = set(payload.member_ids)
        member_ids.add(creator_id)
        
        for m_id in member_ids:
            db.add(ChatMember(chat_id=chat_id, user_id=m_id))
        
        await db.commit()
    else:
        if not payload.recipient_id or payload.recipient_id == creator_id:
            return None
        
        # Check if private chat already exists between these two members
        from sqlalchemy import func
        stmt = (
            select(ChatMember.chat_id)
            .join(Chat, Chat.id == ChatMember.chat_id)
            .where(Chat.is_group == False)
            .where(ChatMember.user_id.in_([creator_id, payload.recipient_id]))
            .group_by(ChatMember.chat_id)
            .having(func.count(ChatMember.user_id) == 2)
        )
        result = await db.execute(stmt)
        found_chat_id = result.scalars().first()
        
        if found_chat_id:
            chat_id = found_chat_id
        else:
            new_chat = Chat(is_group=False)
            db.add(new_chat)
            await db.flush()
            chat_id = new_chat.id
            db.add(ChatMember(chat_id=chat_id, user_id=creator_id))
            db.add(ChatMember(chat_id=chat_id, user_id=payload.recipient_id))
            await db.commit()

    if not chat_id:
        return None

    # Use the helper to get ChatOut and notify via WS
    chat_out = await get_chat_out(db, chat_id)
    
    # Send a specialized "new_chat" WS message if needed, 
    # though get_chat_out already sends "chat_updated".
    # But usually for new chats we want a specific type.
    if chat_out:
        ws_msg = {
            "type": "new_chat",
            "data": chat_out.model_dump(mode='json')
        }
        member_ids = [m.id for m in chat_out.members]
        await manager.broadcast_to_chat(ws_msg, member_ids)

    return chat_out

async def search_users(db: AsyncSession, query: str, exclude_user_id: int):
    # Escape SQL LIKE wildcards to prevent wildcard injection
    safe_query = query.replace("%", "\\%").replace("_", "\\_")
    stmt = select(User).where(User.username.ilike(f"%{safe_query}%")).where(User.id != exclude_user_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_chat(db: AsyncSession, chat_id: int, name: Optional[str], avatar_path: Optional[str], user_id: int):
    # Check if user is member
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None
    
    stmt = select(Chat).where(Chat.id == chat_id)
    result = await db.execute(stmt)
    chat = result.scalars().first()
    if not chat or not chat.is_group:
        return None
    
    if name is not None:
        chat.name = name
    if avatar_path is not None:
        chat.avatar_path = avatar_path
    
    await db.commit()
    return await get_chat_out(db, chat_id)

async def add_member(db: AsyncSession, chat_id: int, member_id: int, user_id: int):
    # Check if user is member
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    res = await db.execute(stmt)
    if not res.scalars().first():
        return None
    
    # Check if already member
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == member_id)
    res = await db.execute(stmt)
    if res.scalars().first():
        return await get_chat_out(db, chat_id)
    
    db.add(ChatMember(chat_id=chat_id, user_id=member_id))
    await db.commit()
    
    chat_out = await get_chat_out(db, chat_id)
    
    # Notify ONLY the new member with "new_chat"
    if chat_out:
        ws_msg = {
            "type": "new_chat",
            "data": chat_out.model_dump(mode='json')
        }
        await manager.broadcast_to_chat(ws_msg, [member_id])
        
    return chat_out

async def remove_member(db: AsyncSession, chat_id: int, member_id: int, user_id: int):
    # Check if user is member (or admin, but for now any member can remove others? Or maybe user can only remove themselves? The request says "удаления участников")
    # Let's allow any member to remove any member for simplicity, or we can restrict.
    # Usually you'd want some admin logic.
    
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    res = await db.execute(stmt)
    if not res.scalars().first():
        return None
    
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == member_id)
    res = await db.execute(stmt)
    member = res.scalars().first()
    if not member:
        return await get_chat_out(db, chat_id)
    
    await db.delete(member)
    await db.commit()
    
    # Notify the removed member that they are no longer in this chat
    ws_msg = {
        "type": "chat_deleted",
        "data": {"chat_id": chat_id}
    }
    await manager.broadcast_to_chat(ws_msg, [member_id])
    
    # Check if any members left
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id)
    res = await db.execute(stmt)
    if not res.scalars().first():
        # Delete chat if no members left
        await delete_chat(db, chat_id, user_id)
        return None

    return await get_chat_out(db, chat_id)

async def delete_chat(db: AsyncSession, chat_id: int, user_id: int):
    # Check if user is member
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    res = await db.execute(stmt)
    if not res.scalars().first():
        return False
    
    # Get members before deletion
    member_ids = await get_chat_member_ids(db, chat_id)
    
    stmt = select(Chat).where(Chat.id == chat_id)
    res = await db.execute(stmt)
    chat = res.scalars().first()
    if not chat:
        return False
    
    await db.delete(chat)
    await db.commit()
    
    # Broadcast deletion
    if member_ids:
        ws_msg = {
            "type": "chat_deleted",
            "data": {"chat_id": chat_id}
        }
        await manager.broadcast_to_chat(ws_msg, member_ids)
        
    return True

async def get_chat_out(db: AsyncSession, chat_id: int) -> Optional[ChatOut]:
    stmt = (
        select(Chat)
        .where(Chat.id == chat_id)
        .options(
            selectinload(Chat.members).joinedload(ChatMember.user)
        )
    )
    result = await db.execute(stmt)
    chat = result.unique().scalars().first()
    if not chat:
        return None
    
    # Get last message
    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .options(
            joinedload(Message.sender),
            selectinload(Message.read_by),
            selectinload(Message.reactions)
        )
    )
    res = await db.execute(stmt)
    last_msg = res.scalars().first()
    
    chat_out = ChatOut(
        id=chat.id,
        name=chat.name,
        avatar_path=chat.avatar_path,
        is_group=chat.is_group,
        created_at=chat.created_at,
        members=[cm.user for cm in chat.members],
        last_message=last_msg
    )
    
    # Notify members of update
    ws_msg = {
        "type": "chat_updated",
        "data": {
            "id": chat_out.id,
            "name": chat_out.name,
            "avatar_path": chat_out.avatar_path,
            "members": [
                {"id": m.id, "username": m.username, "avatar_path": m.avatar_path} for m in chat_out.members
            ]
        }
    }
    member_ids = [m.id for m in chat_out.members]
    await manager.broadcast_to_chat(ws_msg, member_ids)
    
    return chat_out

async def update_chat_avatar(db: AsyncSession, chat_id: int, file: any, filename: str, user_id: int):
    # Check if user is member
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None
    
    stmt = select(Chat).where(Chat.id == chat_id)
    result = await db.execute(stmt)
    chat = result.scalars().first()
    if not chat or not chat.is_group:
        return None
    
    import uuid
    ext = os.path.splitext(filename)[1]
    new_filename = f"chat_{chat_id}_{uuid.uuid4()}{ext}"
    dest_path = os.path.join(settings.AVATAR_DIR, new_filename)
    
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file, buffer)
    
    # Delete old avatar if exists
    if chat.avatar_path:
        old_path = os.path.join(settings.AVATAR_DIR, chat.avatar_path)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass
    
    chat.avatar_path = new_filename
    await db.commit()
    return await get_chat_out(db, chat_id)

async def get_chat_member_ids(db: AsyncSession, chat_id: int) -> List[int]:
    from sqlalchemy import select
    from ..models import ChatMember
    stmt = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def is_chat_member(db: AsyncSession, chat_id: int, user_id: int) -> bool:
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalars().first() is not None
