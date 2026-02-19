import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Messenger API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "DEVELOPMENT_MODE_INSECURE_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]  # Should be restricted in production
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/messenger")
    
    # File Storage
    UPLOAD_DIR: str = "uploads"
    AVATAR_DIR: str = "avatars"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".txt", ".doc", ".docx", ".zip"]
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
