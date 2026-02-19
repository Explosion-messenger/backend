from sqlalchemy.ext.asyncio import AsyncSession
import os
import uuid
import shutil
from ..models import File

UPLOAD_DIR = "uploads"

async def save_file(db: AsyncSession, file_content, filename: str, content_type: str) -> File:
    file_ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file_content, buffer)
    
    file_size = os.path.getsize(file_path)
    
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
    # Optional logic to delete from DB and Disk
    pass
