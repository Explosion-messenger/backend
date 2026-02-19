from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: int
    avatar_path: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class FileOut(BaseModel):
    id: int
    filename: str
    path: str
    mime_type: str
    size: int
    model_config = ConfigDict(from_attributes=True)

class MessageBase(BaseModel):
    text: Optional[str] = None
    file_id: Optional[int] = None

class MessageCreate(MessageBase):
    chat_id: int

class MessageOut(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    sender: UserOut
    text: Optional[str] = None
    file: Optional[FileOut] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ChatBase(BaseModel):
    pass

class ChatCreate(BaseModel):
    recipient_id: Optional[int] = None
    member_ids: Optional[List[int]] = None
    name: Optional[str] = None
    is_group: bool = False

class ChatOut(BaseModel):
    id: int
    name: Optional[str] = None
    is_group: bool = False
    created_at: datetime
    members: List[UserOut]
    last_message: Optional[MessageOut] = None
    model_config = ConfigDict(from_attributes=True)
