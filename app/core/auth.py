"""
JWT Authentication
------------------
Flow:
  POST /api/v1/auth/token  { username, password }  → access_token (JWT)
  All other endpoints require:  Authorization: Bearer <token>

In production swap the hardcoded user for a DB lookup.
"""

import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ── Config ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production-use-openssl-rand-hex-32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# ── Demo user store (swap for DB in production) ────────────────────────────
# Generate a hash with: python -c "from passlib.context import CryptContext; print(CryptContext(['bcrypt']).hash('yourpassword'))"
DEMO_USERS = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash(os.getenv("ADMIN_PASSWORD", "devagent123")),
        "role": "admin",
    }
}


# ── Pydantic models ────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class TokenData(BaseModel):
    username: str | None = None
    role: str | None = None


class User(BaseModel):
    username: str
    role: str


# ── Helpers ────────────────────────────────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> User | None:
    user = DEMO_USERS.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return User(username=user["username"], role=user["role"])


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── FastAPI dependency — use this on any protected route ──────────────────
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception

    user = DEMO_USERS.get(token_data.username)
    if user is None:
        raise credentials_exception
    return User(username=token_data.username, role=token_data.role)


# Optional: admin-only dependency
async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
