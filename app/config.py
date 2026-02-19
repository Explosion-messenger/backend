from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Messenger API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Security
    SECRET_KEY: str = "DEVELOPMENT_MODE_INSECURE_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/messenger"
    
    # Admin Access
    ADMIN_PASSWORD: str = "change_me_immediately"  # Override via ADMIN_PASSWORD env var in production!
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
    
    # File Storage
    UPLOAD_DIR: str = "uploads"
    AVATAR_DIR: str = "avatars"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".txt", ".doc", ".docx", ".zip"]
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
