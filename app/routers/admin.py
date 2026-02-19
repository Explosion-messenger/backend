from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import User
from ..auth import verify_admin_access
from ..services import admin_service, user_service

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/status")
async def get_status(authorized: bool = Depends(verify_admin_access)):
    return {"status": "ok", "message": "Admin authorization active"}

@router.delete("/messages/clear")
async def clear_messages(
    authorized: bool = Depends(verify_admin_access),
    db: AsyncSession = Depends(get_db)
):
    return await admin_service.clear_all_messages(db)

@router.delete("/files/clear")
async def clear_files(
    authorized: bool = Depends(verify_admin_access),
    db: AsyncSession = Depends(get_db)
):
    return await admin_service.clear_all_files(db)

@router.delete("/avatars/clear")
async def clear_avatars(
    authorized: bool = Depends(verify_admin_access),
    db: AsyncSession = Depends(get_db)
):
    return await user_service.clear_all_avatars(db)

@router.delete("/system/wipe")
async def wipe_system(
    authorized: bool = Depends(verify_admin_access),
    db: AsyncSession = Depends(get_db)
):
    """Clear everything: messages, files, chats, and avatars.
    Order: files (nullifies message.file_id first) -> messages -> chats -> avatars
    """
    await admin_service.clear_all_files(db)
    await admin_service.clear_all_messages(db)
    await admin_service.clear_all_chats(db)
    await user_service.clear_all_avatars(db)
    return {"status": "success", "message": "All messages, files, chats, and avatars have been cleared"}
