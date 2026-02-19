from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from ..database import get_db
from ..models import User
from ..schemas import ChatOut, ChatCreate, UserOut
from ..auth import get_current_user
from ..services import chat_service

router = APIRouter()

@router.get("/chats", response_model=List[ChatOut])
async def get_chats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await chat_service.get_user_chats(db, current_user.id)

@router.post("/chats/create", response_model=ChatOut)
async def create_chat(payload: ChatCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat_out = await chat_service.create_chat(db, payload, current_user.id)
    if not chat_out:
        raise HTTPException(status_code=400, detail="Invalid chat creation parameters")
    return chat_out

@router.get("/users", response_model=List[UserOut])
async def search_users(q: str = "", current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await chat_service.search_users(db, q, current_user.id)
