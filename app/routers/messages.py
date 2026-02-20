from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from ..database import get_db
from ..models import User
from ..schemas import MessageOut, MessageCreate, BulkDeleteRequest
from ..auth import get_current_user
from ..services import message_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/messages/{chat_id}", response_model=List[MessageOut])
async def get_messages(chat_id: int, offset: int = 0, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    messages = await message_service.get_messages(db, chat_id, current_user.id, offset)
    if messages is None:
        raise HTTPException(status_code=403, detail="Not a member of this chat")
    return messages

@router.post("/messages/send", response_model=MessageOut)
async def send_message(payload: MessageCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    message = await message_service.send_message(db, payload, current_user.id)
    if not message:
        raise HTTPException(status_code=403, detail="Not a member of this chat")
    return message

@router.delete("/messages/{message_id}")
async def delete_message(message_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    success = await message_service.delete_message(db, message_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or you don't have permission")
    return {"status": "success"}

@router.delete("/messages/bulk")
async def delete_messages_bulk(payload: BulkDeleteRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    success = await message_service.delete_messages(db, payload.message_ids, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete messages")
    return {"status": "success"}

@router.post("/messages/{message_id}/read")
async def mark_as_read(message_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    success = await message_service.mark_as_read(db, message_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "success"}
