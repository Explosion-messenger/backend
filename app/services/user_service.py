from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta
from typing import Optional
import os
import uuid
import shutil
from ..models import User
from ..schemas import UserCreate
from ..auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

AVATAR_DIR = "avatars"

async def register_user(db: AsyncSession, user_in: UserCreate) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == user_in.username))
    if result.scalars().first():
        return None
    
    hashed_password = get_password_hash(user_in.password)
    user = User(username=user_in.username, password_hash=hashed_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user

def create_user_token(user: User):
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

async def update_user_avatar(db: AsyncSession, user: User, file_content, filename: str) -> User:
    file_ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(AVATAR_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file_content, buffer)
    
    # If user had an old avatar, delete it
    if user.avatar_path:
        old_path = os.path.join(AVATAR_DIR, user.avatar_path)
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
        file_path = os.path.join(AVATAR_DIR, user.avatar_path)
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
    if os.path.exists(AVATAR_DIR):
        for filename in os.listdir(AVATAR_DIR):
            file_path = os.path.join(AVATAR_DIR, filename)
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
