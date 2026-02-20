from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, Token, EmailVerification, LoginResponse, TwoFASetup, TwoFAVerify
from ..auth import get_current_user, get_current_admin_user
from ..services import user_service
from ..websockets import manager

router = APIRouter()

@router.post("/register/setup", response_model=TwoFASetup)
async def register_setup(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    if await user_service.check_user_exists(db, user_in.username, user_in.email):
        raise HTTPException(status_code=400, detail="Username or Email already registered")
        
    from ..services.otp_service import generate_2fa_secret, get_2fa_uri
    secret = generate_2fa_secret()
    uri = get_2fa_uri(user_in.username, secret)
    return TwoFASetup(otp_auth_url=uri, secret=secret)

@router.post("/register/confirm", response_model=UserOut)
async def register_confirm(data: UserRegisterConfirm, db: AsyncSession = Depends(get_db)):
    from ..services.otp_service import verify_2fa_code
    
    # 1. Verify 2FA code before creating anything
    if not verify_2fa_code(data.secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
        
    # 2. Final check and create user
    user = await user_service.register_user(db, data, data.secret)
    if not user:
        raise HTTPException(status_code=400, detail="Registration failed (user might have been created by someone else meanwhile)")
    return user


@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await user_service.authenticate_user(db, form_data.username, form_data.password)
    user = result["user"]
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if result["requires_2fa"]:
        return LoginResponse(requires_2fa=True, username=user.username)
        
    token_data = user_service.create_user_token(user)
    return LoginResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        requires_2fa=False,
        username=user.username
    )

@router.post("/login/2fa", response_model=LoginResponse)
async def login_2fa(data: TwoFAVerify, username: str, db: AsyncSession = Depends(get_db)):
    from ..services.otp_service import verify_2fa_code
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    
    if not user or not user.otp_secret:
        raise HTTPException(status_code=401, detail="Invalid session or 2FA not initiated")
        
    if verify_2fa_code(user.otp_secret, data.code):
        if not user.is_2fa_enabled:
            user.is_2fa_enabled = True
            await db.commit()
            
        token_data = user_service.create_user_token(user)
        return LoginResponse(
            access_token=token_data["access_token"],
            token_type=token_data["token_type"],
            requires_2fa=False,
            username=user.username
        )
    else:
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

@router.get("/2fa/setup", response_model=TwoFASetup)
async def setup_2fa(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from ..services.otp_service import generate_2fa_secret, get_2fa_uri
    if current_user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
        
    secret = generate_2fa_secret()
    uri = get_2fa_uri(current_user.username, secret)
    
    # Store temporary secret (caution: this overwrites any existing secret)
    current_user.otp_secret = secret
    await db.commit()
    
    return TwoFASetup(otp_auth_url=uri, secret=secret)

@router.post("/2fa/enable")
async def enable_2fa(data: TwoFAVerify, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from ..services.otp_service import verify_2fa_code
    if not current_user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")
        
    if verify_2fa_code(current_user.otp_secret, data.code):
        current_user.is_2fa_enabled = True
        await db.commit()
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Invalid 2FA code")


@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user = await user_service.update_user_avatar(db, current_user, file.file, file.filename)
    await manager.broadcast_user_update(user.id, user.username, user.avatar_path)
    return user

@router.delete("/me/avatar", response_model=UserOut)
async def delete_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user = await user_service.delete_user_avatar(db, current_user)
    await manager.broadcast_user_update(user.id, user.username, None)
    return user

