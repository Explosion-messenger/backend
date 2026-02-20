import pyotp
from typing import Tuple
from ..config import settings

def generate_email_otp() -> str:
    # Use TOTP with a fixed interval but we'll use it as a one-time code for simplicity
    # or just generate a random string.
    # Standard 6-digit code
    totp = pyotp.TOTP(pyotp.random_base32())
    return totp.now()

def generate_2fa_secret() -> str:
    return pyotp.random_base32()

def get_2fa_uri(username: str, secret: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, 
        issuer_name=settings.PROJECT_NAME
    )

def verify_2fa_code(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
