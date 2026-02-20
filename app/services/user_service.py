from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta
from typing import Optional
import os
import uuid
from fastapi import HTTPException
from ..models import User
from ..schemas import UserCreate
from ..auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from ..config import settings

async def register_user(db: AsyncSession, user_in: UserCreate) -> Optional[User]:
    from sqlalchemy.exc import IntegrityError
    
    # Check if username exists
    stmt = select(User).where(User.username == user_in.username)
    if user_in.email:
        stmt = select(User).where((User.username == user_in.username) | (User.email == user_in.email))
        
    result = await db.execute(stmt)
    if result.scalars().first():
        return None
    
    hashed_password = get_password_hash(user_in.password)
    
    user = User(
        username=user_in.username, 
        email=user_in.email,
        password_hash=hashed_password,
        is_verified=True  # No email verification needed
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        return None
    return user

async def verify_user_email(db: AsyncSession, username: str, code: str) -> bool:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user or user.is_verified:
        return False
    
    if user.otp_secret == code:
        user.is_verified = True
        user.otp_secret = None  # Clear temporary code
        await db.commit()
        return True
    return False

async def authenticate_user(db: AsyncSession, username: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    
    if not user:
        return {"user": None, "requires_2fa": False, "needs_2fa_setup": False}
        
    if not verify_password(password, user.password_hash):
        return {"user": None, "requires_2fa": False, "needs_2fa_setup": False}

    if user.is_2fa_enabled:
        return {"user": user, "requires_2fa": True, "needs_2fa_setup": False}
        
    # Mandatory 2FA: if not enabled, user must set it up
    return {"user": user, "requires_2fa": False, "needs_2fa_setup": True}

async def verify_passwordless_2fa(db: AsyncSession, username: str, code: str) -> Optional[User]:
    from .otp_service import verify_2fa_code
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    
    if not user or not user.is_2fa_enabled or not user.otp_secret:
        return None
        
    if verify_2fa_code(user.otp_secret, code):
        return user
    return None


def create_user_token(user: User):
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

async def update_user_avatar(db: AsyncSession, user: User, file_content, filename: str) -> User:
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Only .jpg, .jpeg, .png are allowed for avatars")

    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(settings.AVATAR_DIR, unique_filename)
    
    # Ensure directory exists
    os.makedirs(settings.AVATAR_DIR, exist_ok=True)
    
    file_size = 0
    with open(file_path, "wb") as buffer:
        while True:
            chunk = file_content.read(1024 * 512)  # 512KB chunks
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > 5 * 1024 * 1024:  # 5MB avatar limit
                buffer.close()
                os.remove(file_path)
                raise HTTPException(status_code=413, detail="Avatar is too large (max 5MB)")
            buffer.write(chunk)
    
    # If user had an old avatar, delete it
    if user.avatar_path:
        old_path = os.path.join(settings.AVATAR_DIR, user.avatar_path)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass

    user.avatar_path = unique_filename
    await db.commit()
    await db.refresh(user)
    return user

async def delete_user_avatar(db: AsyncSession, user: User) -> User:
    if user.avatar_path:
        file_path = os.path.join(settings.AVATAR_DIR, user.avatar_path)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        user.avatar_path = None
        await db.commit()
        await db.refresh(user)
    return user

async def clear_all_avatars(db: AsyncSession):
    # 1. Delete all files in the directory
    if os.path.exists(settings.AVATAR_DIR):
        for filename in os.listdir(settings.AVATAR_DIR):
            file_path = os.path.join(settings.AVATAR_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except:
                pass
    
    # 2. Reset avatar_path for all users in DB
    from sqlalchemy import update
    await db.execute(update(User).values(avatar_path=None))
    await db.commit()
    return {"status": "success", "message": "All avatars cleared"}
