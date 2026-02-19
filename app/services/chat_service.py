from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional
from ..models import Chat, ChatMember, User, Message
from ..schemas import ChatCreate, ChatOut
from ..websockets import manager

async def get_user_chats(db: AsyncSession, user_id: int) -> List[ChatOut]:
    stmt = (
        select(Chat)
        .join(ChatMember)
        .where(ChatMember.user_id == user_id)
        .options(
            selectinload(Chat.members).joinedload(ChatMember.user),
            selectinload(Chat.messages).options(joinedload(Message.sender))
        )
    )
    result = await db.execute(stmt)
    chats = result.unique().scalars().all()
    
    out = []
    for chat in chats:
        members = [cm.user for cm in chat.members]
        last_msg = None
        if chat.messages:
            last_msg = sorted(chat.messages, key=lambda x: x.created_at, reverse=True)[0]
        
        out.append(ChatOut(
            id=chat.id,
            name=chat.name,
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
        
        chat = Chat(name=payload.name, is_group=True)
        db.add(chat)
        await db.flush()
        chat_id = chat.id
        
        member_ids = set(payload.member_ids)
        member_ids.add(creator_id)
        
        for m_id in member_ids:
            db.add(ChatMember(chat_id=chat.id, user_id=m_id))
        
        await db.commit()
    else:
        if not payload.recipient_id or payload.recipient_id == creator_id:
            return None
        
        # Check if exists
        stmt = (
            select(Chat)
            .join(ChatMember, Chat.id == ChatMember.chat_id)
            .where(ChatMember.user_id == creator_id)
            .where(Chat.is_group == False)
        )
        result = await db.execute(stmt)
        user_chats = result.scalars().all()
        
        found_chat_id = None
        for chat_obj in user_chats:
            member_stmt = select(ChatMember).where(ChatMember.chat_id == chat_obj.id)
            member_result = await db.execute(member_stmt)
            members = member_result.scalars().all()
            
            m_ids = [m.user_id for m in members]
            if len(m_ids) == 2 and payload.recipient_id in m_ids:
                found_chat_id = chat_obj.id
                break
        
        if found_chat_id:
            chat_id = found_chat_id
        else:
            chat = Chat(is_group=False)
            db.add(chat)
            await db.flush()
            chat_id = chat.id
            db.add(ChatMember(chat_id=chat.id, user_id=creator_id))
            db.add(ChatMember(chat_id=chat.id, user_id=payload.recipient_id))
            await db.commit()

    # Refetch
    stmt = (
        select(Chat)
        .where(Chat.id == chat_id)
        .options(
            selectinload(Chat.members).joinedload(ChatMember.user),
            selectinload(Chat.messages).options(joinedload(Message.sender))
        )
    )
    result = await db.execute(stmt)
    chat = result.unique().scalars().first()
    
    last_msg = None
    if chat.messages:
        last_msg = sorted(chat.messages, key=lambda x: x.created_at, reverse=True)[0]

    chat_out = ChatOut(
        id=chat.id,
        name=chat.name,
        is_group=chat.is_group,
        created_at=chat.created_at,
        members=[cm.user for cm in chat.members],
        last_message=last_msg
    )

    # Notify via WebSocket
    ws_msg = {
        "type": "new_chat",
        "data": {
            "id": chat_out.id,
            "name": chat_out.name,
            "is_group": chat_out.is_group,
            "created_at": chat_out.created_at.isoformat(),
            "members": [
                {
                    "id": m.id,
                    "username": m.username,
                    "avatar_path": m.avatar_path
                } for m in chat_out.members
            ],
            "last_message": None
        }
    }
    member_ids = [m.id for m in chat_out.members]
    await manager.broadcast_to_chat(ws_msg, member_ids)

    return chat_out

async def search_users(db: AsyncSession, query: str, exclude_user_id: int):
    stmt = select(User).where(User.username.ilike(f"%{query}%")).where(User.id != exclude_user_id)
    result = await db.execute(stmt)
    return result.scalars().all()
