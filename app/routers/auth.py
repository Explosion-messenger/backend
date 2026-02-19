from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, Token
from ..auth import get_current_user, get_current_admin_user
from ..services import user_service
import os

router = APIRouter()

@router.post("/register", response_model=UserOut)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await user_service.register_user(db, user_in)
    if not user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await user_service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_service.create_user_token(user)

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Limit to 5MB for avatars
    MAX_SIZE = 5 * 1024 * 1024
    
    user = await user_service.update_user_avatar(db, current_user, file.file, file.filename)
    
    # Check size
    file_path = os.path.join("avatars", user.avatar_path)
    if os.path.getsize(file_path) > MAX_SIZE:
        os.remove(file_path)
        user.avatar_path = None
        await db.commit()
        raise HTTPException(status_code=413, detail="Avatar image too large")
        
    return user

@router.delete("/me/avatar", response_model=UserOut)
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await user_service.delete_user_avatar(db, current_user)

@router.delete("/admin/avatars/clear")
async def clear_avatars(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    return await user_service.clear_all_avatars(db)
