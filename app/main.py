from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from jose import jwt, JWTError

from .database import engine, Base
from .websockets import manager
from .auth import SECRET_KEY, ALGORITHM, get_current_user
from .routers import auth, chats, messages, files

app = FastAPI(title="Messenger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create upload directory
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

AVATAR_DIR = "avatars"
if not os.path.exists(AVATAR_DIR):
    os.makedirs(AVATAR_DIR)

app.mount("/files/download", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/avatars", StaticFiles(directory=AVATAR_DIR), name="avatars")

app.include_router(auth.router, tags=["auth"])
app.include_router(chats.router, tags=["chats"])
app.include_router(messages.router, tags=["messages"])
app.include_router(files.router, tags=["files"])

@app.get("/")
async def root():
    return {"message": "Messenger API is running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    print(f"DEBUG: WS connection attempt with token: {token[:10]}...")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            logger.warning("WS connection failed: user_id missing in token")
            await websocket.close(code=4003)
            return
    except JWTError as e:
        logger.error(f"WS connection failed: JWT Error: {str(e)}")
        await websocket.close(code=4003)
        return
    except Exception as e:
        logger.error(f"WS connection failed: Unexpected error: {str(e)}")
        await websocket.close(code=4003)
        return

    logger.info(f"WS connection authorized for user_id: {user_id}")
    await manager.connect(user_id, websocket)
    
    # Send initial list of online users
    online_users = manager.get_online_users()
    await manager.send_personal_message({
        "type": "online_list",
        "data": online_users
    }, user_id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"WS disconnected for user_id: {user_id}")
        await manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WS error for user_id {user_id}: {str(e)}")
        await manager.disconnect(user_id, websocket)
