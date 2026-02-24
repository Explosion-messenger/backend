from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File as FastAPIFile
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, Token, EmailVerification, LoginResponse, TwoFASetup, TwoFAVerify, UserRegisterConfirm, PasswordlessLogin
from ..auth import get_current_user, get_current_admin_user
from ..services import user_service
from ..websockets import manager

router = APIRouter()

@router.post("/register/setup", response_model=TwoFASetup)
async def register_setup(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    if await user_service.check_user_exists(db, user_in.username, user_in.email):
        raise HTTPException(status_code=400, detail="Username or Email already registered")
        
    from ..services.otp_service import generate_2fa_secret, get_2fa_uri
    from ..auth import create_access_token
    from datetime import timedelta
    
    secret = generate_2fa_secret()
    uri = get_2fa_uri(user_in.username, secret)
    
    setup_token = create_access_token(
        data={"sub": user_in.username, "email": user_in.email, "password": user_in.password, "secret": secret},
        expires_delta=timedelta(minutes=10),
        token_type="setup"
    )
    return TwoFASetup(otp_auth_url=uri, secret=secret, setup_token=setup_token)

@router.post("/register/confirm", response_model=UserOut)
async def register_confirm(data: UserRegisterConfirm, db: AsyncSession = Depends(get_db)):
    from ..services.otp_service import verify_2fa_code
    from jose import jwt, JWTError
    from ..auth import SECRET_KEY, ALGORITHM
    
    try:
        payload = jwt.decode(data.setup_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "setup":
            raise HTTPException(status_code=400, detail="Invalid token type")
        username = payload.get("sub")
        email = payload.get("email")
        password = payload.get("password")
        secret = payload.get("secret")
    except JWTError:
        raise HTTPException(status_code=400, detail="Registration session expired or invalid")
        
    if not verify_2fa_code(secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")
        
    user_data = UserCreate(username=username, email=email, password=password)
    user = await user_service.register_user(db, user_data, secret)
    if not user:
        raise HTTPException(status_code=400, detail="Registration failed (user might exist now)")
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
        from ..auth import create_access_token
        from datetime import timedelta
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
async def login_2fa(data: TwoFAVerify, token: str = Depends(OAuth2PasswordBearer(tokenUrl="login", auto_error=False)), db: AsyncSession = Depends(get_db)):
    from ..services.otp_service import verify_2fa_code
    from jose import jwt, JWTError
    from ..auth import SECRET_KEY, ALGORITHM, create_access_token
    
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

@router.post("/login/2fa/passwordless", response_model=LoginResponse)
async def login_2fa_passwordless(data: PasswordlessLogin, db: AsyncSession = Depends(get_db)):
    user = await user_service.verify_passwordless_2fa(db, data.username, data.code)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or 2FA code")
        
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

