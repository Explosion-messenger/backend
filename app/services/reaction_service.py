from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..models import MessageReaction, Message, ChatMember
from ..websockets import manager

async def toggle_reaction(db: AsyncSession, message_id: int, user_id: int, emoji: str):
    # Check if message exists and user is member of that chat
    stmt = select(Message.chat_id).where(Message.id == message_id)
    result = await db.execute(stmt)
    chat_id = result.scalar()
    
    if not chat_id:
        return None
        
    stmt = select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    result = await db.execute(stmt)
    if not result.scalars().first():
        return None
        
    # Check if reaction exists
    stmt = select(MessageReaction).where(
        MessageReaction.message_id == message_id,
        MessageReaction.user_id == user_id,
        MessageReaction.emoji == emoji
    )
    result = await db.execute(stmt)
    reaction = result.scalars().first()
    
    if reaction:
        await db.delete(reaction)
        action = "removed"
    else:
        reaction = MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji)
        db.add(reaction)
        action = "added"
        
    await db.commit()
    
    # Broadcast update
    from .chat_service import get_chat_member_ids
    member_ids = await get_chat_member_ids(db, chat_id)
    
    ws_msg = {
        "type": "message_reaction",
        "data": {
            "message_id": message_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "emoji": emoji,
            "action": action
        }
    }
    await manager.broadcast_to_chat(ws_msg, member_ids)
    
    return {"status": "success", "action": action}
