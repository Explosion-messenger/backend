from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os
import logging
from jose import jwt, JWTError

from .config import settings
from .database import engine, Base
from .websockets import manager
from .auth import SECRET_KEY, ALGORITHM, get_current_user
from .routers import auth, chats, messages, files

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
app.mount("/files/download", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/avatars", StaticFiles(directory=settings.AVATAR_DIR), name="avatars")

# Include routers
app.include_router(auth.router, tags=["auth"])
app.include_router(chats.router, tags=["chats"])
app.include_router(messages.router, tags=["messages"])
app.include_router(files.router, tags=["files"])

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
            # We only receive messages for keep-alive or future features
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WS error: {str(e)}")
        await manager.disconnect(user_id, websocket)
