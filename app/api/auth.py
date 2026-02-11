from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import wraps
import hashlib
from jose import JWTError, jwt
import bcrypt  # Replaced passlib with direct bcrypt
from flask import request, jsonify, g
import httpx

from app.config import settings
from app.db import queries
from app.db.database import db

# ===== Password Functions =====

def hash_password(password: str) -> str:
    """Hash a password using bcrypt (Python 3.13 compatible)"""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password using bcrypt"""
    try:
        if not hashed_password:
            return False
        plain_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        # Failssafe for invalid hash formats or other errors
        return False


# ===== JWT Token Functions =====

def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None):
    """Create a refresh token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt, expire

def decode_token(token: str) -> Dict[str, Any]:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise Exception("Invalid token")

def hash_token(token: str) -> str:
    """Hash token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()


# ===== Auth Decorator (Flask) =====

def token_required(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")
        
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0] == "Bearer":
                token = parts[1]
        
        if not token:
            return jsonify({"detail": "Token is missing"}), 401
        
        try:
            # Verify token
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("sub")
            token_type = payload.get("type")
            
            if not user_id or token_type != "access":
                return jsonify({"detail": "Invalid token"}), 401
            
            # Ensure DB connection
            if not db.client:
                await db.connect()
                
            # Fetch user
            user = await queries.get_user_by_id(db, user_id)
            if not user:
                return jsonify({"detail": "User not found"}), 401
            
            # Store in g context
            g.current_user = user
            
        except JWTError:
            return jsonify({"detail": "token is invalid"}), 401
        except Exception as e:
            return jsonify({"detail": str(e)}), 401
        
        return await f(*args, **kwargs)
    return decorated


# ===== Helper Functions =====

async def authenticate_user(db, email, password):
    user = await queries.get_user_by_email(db, email)
    if not user:
        return False
    if not verify_password(password, user["password_hash"]):
        return False
    return user

async def get_google_user_info(access_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        return response.json()

async def get_github_user_info(access_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
        )
        return response.json()
