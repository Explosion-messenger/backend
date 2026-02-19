from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from sqlalchemy.ext.asyncio import AsyncSession
import os
from ..database import get_db
from ..schemas import FileOut
from ..auth import get_current_user
from ..services import file_service

router = APIRouter()

@router.post("/files/upload", response_model=FileOut)
async def upload_file(file: UploadFile = FastAPIFile(...), current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Limit to 50MB
    MAX_SIZE = 50 * 1024 * 1024
    
    db_file = await file_service.save_file(db, file.file, file.filename, file.content_type)
    
    if db_file.size > MAX_SIZE:
        file_path = os.path.join("uploads", db_file.path)
        if os.path.exists(file_path):
            os.remove(file_path)
        await db.delete(db_file)
        await db.commit()
        raise HTTPException(status_code=413, detail="File too large")
        
    return db_file
