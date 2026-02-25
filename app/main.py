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

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .limiter import limiter

# Initialize Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Exception Handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Only trap if it's not a rate limit exception (handled natively above)
    if isinstance(exc, RateLimitExceeded):
        return await _rate_limit_exceeded_handler(request, exc)
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

# Include routers with version prefix
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(chats.router, prefix=settings.API_V1_STR, tags=["chats"])
app.include_router(messages.router, prefix=settings.API_V1_STR, tags=["messages"])
app.include_router(files.router, prefix=settings.API_V1_STR, tags=["files"])
app.include_router(admin.router, prefix=settings.API_V1_STR + "/admin", tags=["admin"])

@app.get("/")
async def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs"
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
                await manager.handle_message(user_id, msg, websocket)
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Error processing WS message: {e}")
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WS error: {str(e)}")
        await manager.disconnect(user_id, websocket)

