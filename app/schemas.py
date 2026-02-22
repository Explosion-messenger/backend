from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")

class UserCreate(UserBase):
    email: Optional[str] = Field(None, description="User email (optional)")
    password: str = Field(..., min_length=6, max_length=100, description="User password")

class UserRegisterConfirm(UserCreate):
    secret: str = Field(..., description="The 2FA secret generated in setup step")
    code: str = Field(..., description="The verification code from the authenticator app")

class UserOut(UserBase):
    id: int
    email: Optional[str] = None
    avatar_path: Optional[str] = None
    is_admin: bool = False
    is_verified: bool = False
    is_2fa_enabled: bool = False
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ChatMemberOut(UserOut):
    is_chat_admin: bool = False

class EmailVerification(BaseModel):
    username: str
    code: str

class TwoFASetup(BaseModel):
    otp_auth_url: str
    secret: str

class TwoFAVerify(BaseModel):
    code: str

class PasswordlessLogin(BaseModel):
    username: str
    code: str

class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    requires_2fa: bool = False
    username: Optional[str] = None

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
    text: Optional[str] = Field(None, max_length=4000)
    file_id: Optional[int] = None

class MessageCreate(MessageBase):
    chat_id: int

class MessageReadOut(BaseModel):
    user_id: int
    read_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MessageReactionOut(BaseModel):
    id: int
    user_id: int
    emoji: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MessageOut(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    sender: UserOut
    text: Optional[str] = None
    file: Optional[FileOut] = None
    created_at: datetime
    read_by: List[MessageReadOut] = []
    reactions: List[MessageReactionOut] = []
    model_config = ConfigDict(from_attributes=True)

class ReactionToggle(BaseModel):
    emoji: str

class ChatCreate(BaseModel):
    recipient_id: Optional[int] = Field(None, description="For private chats")
    member_ids: Optional[List[int]] = Field(None, description="For group chats")
    name: Optional[str] = Field(None, max_length=100, description="Group name")
    is_group: bool = False

class ChatOut(BaseModel):
    id: int
    name: Optional[str] = None
    avatar_path: Optional[str] = None
    is_group: bool = False
    created_at: datetime
    members: List[ChatMemberOut]
    last_message: Optional[MessageOut] = None
    model_config = ConfigDict(from_attributes=True)

class ChatUpdate(BaseModel):
    name: Optional[str] = None
    avatar_path: Optional[str] = None

class AddMember(BaseModel):
    user_id: int

class MemberAdminUpdate(BaseModel):
    user_id: int
    is_admin: bool

class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None

class BulkDeleteRequest(BaseModel):
    message_ids: List[int]
