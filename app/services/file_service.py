import aiofiles
import os
import uuid
import logging
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..models import File
from ..config import settings

logger = logging.getLogger(__name__)

async def save_file(db: AsyncSession, file_content, filename: str, content_type: str) -> File:
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File extension {file_ext} not allowed")

    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)
    
    # Ensure directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    
    file_size = 0
    async with aiofiles.open(file_path, "wb") as buffer:
        while True:
            chunk = await file_content.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > settings.MAX_FILE_SIZE:
                await buffer.close()
                os.remove(file_path)
                raise HTTPException(status_code=413, detail="File too large")
            await buffer.write(chunk)
    
    db_file = File(
        filename=filename,
        path=unique_filename,
        mime_type=content_type,
        size=file_size
    )
    db.add(db_file)
    await db.commit()
    await db.refresh(db_file)
    return db_file

async def delete_file(db: AsyncSession, file_id: int) -> bool:
    """Delete a file record from the DB and its physical file from disk."""
    result = await db.execute(select(File).where(File.id == file_id))
    db_file = result.scalars().first()
    if not db_file:
        return False

    file_path = os.path.join(settings.UPLOAD_DIR, db_file.path)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    await db.delete(db_file)
    await db.commit()
    return True
