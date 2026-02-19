from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
import os
import shutil
from ..models import Message, File, User, Chat, ChatMember
from ..config import settings

async def clear_all_messages(db: AsyncSession):
    """Deletes all messages from the database."""
    await db.execute(delete(Message))
    await db.commit()
    return {"status": "success", "message": "All messages cleared"}

async def clear_all_files(db: AsyncSession):
    """Deletes all uploaded files from DB and disk."""
    # 1. Clear file_id pointers in messages to avoid FK violation
    from sqlalchemy import update
    await db.execute(update(Message).values(file_id=None))
    
    # 2. Delete files from disk
    if os.path.exists(settings.UPLOAD_DIR):
        for filename in os.listdir(settings.UPLOAD_DIR):
            file_path = os.path.join(settings.UPLOAD_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
    
    # 3. Clear File table in DB
    await db.execute(delete(File))
    await db.commit()
    return {"status": "success", "message": "All uploaded files cleared"}

async def clear_all_chats(db: AsyncSession):
    """Deletes all chats and chat members from the database."""
    # Order matters if there are FKs, though Message deletion should happen first
    await db.execute(delete(ChatMember))
    await db.execute(delete(Chat))
    await db.commit()
    return {"status": "success", "message": "All chats and members cleared"}

async def clear_database(db: AsyncSession):
    """Wipe all messages, files, and chats (Full system reset)."""
    await clear_all_messages(db)
    await clear_all_files(db)
    await clear_all_chats(db)
    # We keep users, but clear their metadata if needed. 
    return {"status": "success", "message": "System state reset: all messages, files, and chats wiped"}
