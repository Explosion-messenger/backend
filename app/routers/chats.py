from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from ..database import get_db
from ..models import User
from ..schemas import ChatOut, ChatCreate, UserOut, ChatUpdate, AddMember, StatusResponse
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

@router.patch("/chats/{chat_id}", response_model=ChatOut)
async def update_chat(chat_id: int, payload: ChatUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await chat_service.update_chat(db, chat_id, payload.name, payload.avatar_path, current_user.id)
    if not chat:
        raise HTTPException(status_code=403, detail="Forbidden or chat not found")
    return chat

@router.post("/chats/{chat_id}/members", response_model=ChatOut)
async def add_member(chat_id: int, payload: AddMember, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await chat_service.add_member(db, chat_id, payload.user_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=403, detail="Forbidden or chat not found")
    return chat

@router.delete("/chats/{chat_id}/members/{member_id}", response_model=ChatOut)
async def remove_member(chat_id: int, member_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await chat_service.remove_member(db, chat_id, member_id, current_user.id)
    if chat is None:
        # Chat might be deleted if last member left, or forbidden
        return StatusResponse(status="ok", message="Member removed or chat deleted")
    return chat

@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    success = await chat_service.delete_chat(db, chat_id, current_user.id)
    if not success:
        raise HTTPException(status_code=403, detail="Forbidden or chat not found")
    return {"status": "ok"}

@router.post("/chats/{chat_id}/avatar", response_model=ChatOut)
async def upload_chat_avatar(
    chat_id: int,
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    chat = await chat_service.update_chat_avatar(db, chat_id, file.file, file.filename, current_user.id)
    if not chat:
        raise HTTPException(status_code=403, detail="Forbidden or chat not found")
    return chat
