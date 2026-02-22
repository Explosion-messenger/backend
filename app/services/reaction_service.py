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
        
    # Check if a reaction already exists for this user/emoji
    stmt = select(MessageReaction).where(
        MessageReaction.message_id == message_id,
        MessageReaction.user_id == user_id,
        MessageReaction.emoji == emoji
    )
    result = await db.execute(stmt)
    existing_reaction = result.scalars().first()
    
    if existing_reaction:
        # If it's the SAME emoji, toggle it off (standard behavior)
        await db.delete(existing_reaction)
        action = "removed"
    else:
        # If it's a DIFFERENT emoji, first remove ANY existing reaction by this user
        # to enforce "one reaction per user" rule
        delete_stmt = select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user_id
        )
        delete_result = await db.execute(delete_stmt)
        for old_react in delete_result.scalars().all():
            await db.delete(old_react)
            # We notify clients that the OLD reaction was removed
            ws_msg_old = {
                "type": "message_reaction",
                "data": {
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "emoji": old_react.emoji,
                    "action": "removed"
                }
            }
            await manager.broadcast_to_chat(ws_msg_old, member_ids)

        # Now add the new one
        reaction = MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji)
        db.add(reaction)
        action = "added"
    
    await db.commit()
    
    # Broadcast the CURRENT (added) action
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
