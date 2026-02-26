from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import os
from ..database import get_db
from ..schemas import FileOut
from ..auth import get_current_user
from ..services import file_service
from ..config import settings

router = APIRouter()

@router.post("/files/upload", response_model=FileOut)
async def upload_file(file: UploadFile = FastAPIFile(...), current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    db_file = await file_service.save_file(db, file, file.filename, file.content_type)
    return db_file

@router.get("/files/download/{file_path:path}")
async def download_file(
    file_path: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Sanitize: only allow the basename to prevent path traversal (e.g. ../../etc/passwd)
    safe_name = os.path.basename(file_path)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid file path")

    full_path = os.path.join(settings.UPLOAD_DIR, safe_name)
    resolved = os.path.realpath(full_path)
    upload_dir_resolved = os.path.realpath(settings.UPLOAD_DIR)

    if not resolved.startswith(upload_dir_resolved + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(resolved)
