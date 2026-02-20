from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from jose import jwt, JWTError

from .config import settings
from .database import engine, Base, AsyncSessionLocal
from .websockets import manager
from .auth import SECRET_KEY, ALGORITHM, get_current_user
from .routers import auth, chats, messages, files, admin
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)

# CORS — allows frontend and admin panel dev servers to reach the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )

# Ensure required directories exist
for directory in [settings.UPLOAD_DIR, settings.AVATAR_DIR]:
    os.makedirs(directory, exist_ok=True)

# Mount static files with some security consideration
# In production, these should be served by Nginx or S3
# Avatars remain public for now, but uploads are protected via authenticated endpoint in files.py
app.mount("/avatars", StaticFiles(directory=settings.AVATAR_DIR), name="avatars")

# Include routers
app.include_router(auth.router, tags=["auth"])
app.include_router(chats.router, tags=["chats"])
app.include_router(messages.router, tags=["messages"])
app.include_router(files.router, tags=["files"])
app.include_router(admin.router, tags=["admin"])

@app.get("/")
async def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running"
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            await websocket.close(code=4003)
            return
    except (JWTError, Exception) as e:
        logger.warning(f"WS auth failed: {str(e)}")
        await websocket.close(code=4003)
        return

    logger.info(f"WS authorized: user {user_id}")
    await manager.connect(user_id, websocket)
    
    try:
        # Initial state
        await manager.send_personal_message({
            "type": "online_list",
            "data": manager.get_online_users()
        }, user_id)

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "typing":
                    chat_id = msg.get("chat_id")
                    is_typing = msg.get("is_typing", False)
                    if chat_id:
                        try:
                            from .services.chat_service import get_chat_member_ids
                            from .models import User as DBUser
                            from sqlalchemy import select
                            async with AsyncSessionLocal() as db:
                                # Get members and typing user's name
                                member_ids_task = get_chat_member_ids(db, chat_id)
                                user_name_stmt = select(DBUser.username).where(DBUser.id == user_id)
                                user_name_result = await db.execute(user_name_stmt)
                                user_name = user_name_result.scalar()
                                member_ids = await member_ids_task

                                if user_name:
                                    ws_msg = {
                                        "type": "typing",
                                        "data": {
                                            "chat_id": chat_id,
                                            "user_id": user_id,
                                            "username": user_name,
                                            "is_typing": is_typing
                                        }
                                    }
                                    recipients = [m_id for m_id in member_ids if m_id != user_id]
                                    await manager.broadcast_to_chat(ws_msg, recipients)
                        except Exception as inner_e:
                            logger.error(f"Typing broadcast failure for user {user_id} in chat {chat_id}: {inner_e}")
                elif msg.get("type") == "user_status_update":
                    new_status = msg.get("status")
                    if new_status:
                        await manager.update_user_status(user_id, new_status)
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Error processing WS message: {e}")
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WS error: {str(e)}")
        await manager.disconnect(user_id, websocket)
