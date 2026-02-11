"""
Pydantic models for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ===== Enums =====

class SessionType(str, Enum):
    CHAT = "chat"
    TASK = "task"


class StrategyType(str, Enum):
    SINGLE_STEP = "single_step"
    MULTI_STEP = "multi_step"
    IMAGE_UNDERSTANDING = "image_understanding"


class OAuthProvider(str, Enum):
    GOOGLE = "google"
    GITHUB = "github"
    APPLE = "apple"


class TokenType(str, Enum):
    REFRESH = "refresh"
    API_KEY = "api_key"


# ===== User Models =====

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    age: Optional[int] = Field(None, ge=13)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    age: Optional[int] = None
    is_verified: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None


# ===== Authentication Models =====

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str  # user_id
    exp: int  # expiration timestamp


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ===== OTP Models =====

class OTPRequest(BaseModel):
    """Sent by frontend to request OTP"""
    email: EmailStr

class OTPVerify(BaseModel):
    """Sent by frontend to verify OTP"""
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=6)

class OTPResponse(BaseModel):
    """Returned when OTP is sent"""
    message: str
    email: str
    requires_otp: bool = True
    expires_in_minutes: int = 5


# ===== OAuth Models =====

class OAuthCallbackResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


# ===== Voice Verification Models =====

class VoiceEnrollmentResponse(BaseModel):
    id: str
    user_id: str
    sample_count: int
    message: str


class VoiceVerificationRequest(BaseModel):
    email: EmailStr


class VoiceVerificationResponse(BaseModel):
    success: bool
    confidence_score: Optional[float] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[UserResponse] = None
    message: str


# ===== Session Models =====

class SessionCreate(BaseModel):
    session_type: SessionType = SessionType.CHAT


class SessionResponse(BaseModel):
    id: str
    user_id: str
    session_type: str
    created_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


# ===== Request Models =====

class RequestCreate(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=5000)


class RequestResponse(BaseModel):
    id: str
    session_id: str
    user_prompt: str
    intent: Optional[str] = None
    strategy: Optional[str] = None
    created_at: Optional[datetime] = None


# ===== Response Models =====

class FinalResponse(BaseModel):
    id: str
    request_id: str
    final_response: str
    models_used: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    estimated_cost: Optional[float] = None
    created_at: Optional[datetime] = None


# ===== Step Models =====

class StepResponse(BaseModel):
    id: str
    request_id: str
    step_type: Optional[str] = None
    model_name: Optional[str] = None
    input_prompt: Optional[str] = None
    output_text: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: Optional[datetime] = None


# ===== Error Models =====

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
