from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from jose import jwt, JWTError

from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, LoginResponse, TwoFASetup, TwoFAVerify, UserRegisterConfirm, PasswordlessLogin, PasswordlessLoginRequest
from ..auth import get_current_user, get_current_admin_user, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM
from ..services import user_service
from ..services.otp_service import generate_2fa_secret, get_2fa_uri, verify_2fa_code
from ..websockets import manager
from ..limiter import limiter

router = APIRouter()

@router.post("/register/setup", summary="Step 1: Get OTP for registration", response_model=TwoFASetup)
@limiter.limit("5/minute")
async def register_setup(request: Request, user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    stmt = select(User).where((User.username == user_in.username) | (User.email == user_in.email))
    result = await db.execute(stmt)
    existing_user = result.scalars().first()
    
    if existing_user:
        if existing_user.is_verified:
            raise HTTPException(status_code=400, detail="Username or Email already registered")
        else:
            # Unverified user. Delete to allow fresh registration.
            await db.delete(existing_user)
            await db.commit()
            

    secret = generate_2fa_secret()
    uri = get_2fa_uri(user_in.username, secret)
    
    # Create the user in unverified state
    user = await user_service.register_user(db, user_in, secret, is_verified=False)
    if not user:
        raise HTTPException(status_code=400, detail="Registration failed")

    setup_token = create_access_token(
        data={"user_id": user.id},
        expires_delta=timedelta(minutes=10),
        token_type="setup"
    )
    return TwoFASetup(otp_auth_url=uri, secret=secret, setup_token=setup_token)

@router.post("/register/confirm", summary="Step 2: Verify OTP and create user", response_model=UserOut)
@limiter.limit("5/minute")
async def register_confirm(request: Request, data: UserRegisterConfirm, db: AsyncSession = Depends(get_db)):

    try:
        payload = jwt.decode(data.setup_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "setup":
            raise HTTPException(status_code=400, detail="Invalid token type")
        user_id = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=400, detail="Registration session expired or invalid")
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user or user.is_verified:
        raise HTTPException(status_code=400, detail="Invalid registration session or user already verified")

    if not verify_2fa_code(user.otp_secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
        
    user.is_verified = True
    user.is_2fa_enabled = True
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await user_service.authenticate_user(db, form_data.username, form_data.password)
    user = result["user"]
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if result["requires_2fa"]:

        preauth = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=5),
            token_type="preauth"
        )
        return LoginResponse(
            access_token=preauth,
            token_type="bearer",
            requires_2fa=True,
            username=user.username
        )
        
    token_data = user_service.create_user_token(user)
    return LoginResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        requires_2fa=False,
        username=user.username
    )

@router.post("/login/2fa", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login_2fa(request: Request, data: TwoFAVerify, token: str = Depends(OAuth2PasswordBearer(tokenUrl="login", auto_error=False)), db: AsyncSession = Depends(get_db)):

    
    if not token:
        raise HTTPException(status_code=401, detail="Pre-auth token required")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "preauth":
            raise HTTPException(status_code=401, detail="Invalid token type")
        username = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Login session expired")
    
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

@router.post("/login/passwordless", summary="Step 1: Initiate passwordless login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login_passwordless_init(request: Request, data: PasswordlessLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalars().first()
    if not user or not user.is_2fa_enabled:
        raise HTTPException(status_code=401, detail="User not found or 2FA not enabled for this node")
    

    preauth = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=5),
        token_type="preauth"
    )
    
    # We return requires_2fa=True. The frontend will then ask for the code.
    return LoginResponse(
        access_token=preauth,
        token_type="bearer",
        requires_2fa=True, 
        username=user.username
    )

@router.post("/login/2fa/passwordless", summary="Step 2: Verify code for passwordless login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login_passwordless_verify(request: Request, data: PasswordlessLogin, db: AsyncSession = Depends(get_db)):
    user = await user_service.verify_passwordless_2fa(db, data.username, data.code)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid neural bypass code")
        
    token_data = user_service.create_user_token(user)
    return LoginResponse(
        access_token=token_data["access_token"],
        token_type=token_data["token_type"],
        requires_2fa=False,
        username=user.username
    )



@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user = await user_service.update_user_avatar(db, current_user, file, file.filename)
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

