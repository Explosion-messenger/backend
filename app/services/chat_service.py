from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional
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
                .options(joinedload(Message.sender), joinedload(Message.file))
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
    # Escape SQL LIKE wildcards to prevent wildcard injection
    safe_query = query.replace("%", "\\%").replace("_", "\\_")
    stmt = select(User).where(User.username.ilike(f"%{safe_query}%")).where(User.id != exclude_user_id)
    result = await db.execute(stmt)
    return result.scalars().all()
