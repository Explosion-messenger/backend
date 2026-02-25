from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import secrets
from pydantic import Field

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Messenger API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security
    # In production, ALWAYS set SECRET_KEY in .env
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/messenger"
    
    # Admin Access
    # In production, ALWAYS set ADMIN_PASSWORD in .env
    ADMIN_PASSWORD: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:5173",
        "https://localhost",
        "https://messenger.app",
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
    ]
    
    # File Storage
    UPLOAD_DIR: str = "uploads"
    AVATAR_DIR: str = "avatars"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".txt", ".doc", ".docx", ".zip"]

    # SMTP Settings (For development using Mailtrap or similar)
    SMTP_HOST: str = "smtp.mailtrap.io"
    SMTP_PORT: int = 2525
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@messenger.app"
    
    # OTP Settings
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = 10
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
