"""
Database query functions - MongoDB operations
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid


def _new_id() -> str:
    """Generate a new string UUID for document IDs"""
    return str(uuid.uuid4())


def _now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


# ===== User Queries =====

async def create_user(db, email: str, password_hash: str, full_name: Optional[str], age: Optional[int]) -> Dict:
    """Create a new user"""
    doc = {
        "_id": _new_id(),
        "email": email,
        "password_hash": password_hash,
        "full_name": full_name,
        "age": age,
        "is_verified": False,
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now()
    }
    await db.db.users.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_user_by_email(db, email: str) -> Optional[Dict]:
    """Get user by email"""
    doc = await db.db.users.find_one({"email": email, "is_active": True})
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


async def get_user_by_id(db, user_id) -> Optional[Dict]:
    """Get user by ID"""
    uid = str(user_id)
    doc = await db.db.users.find_one({"_id": uid, "is_active": True})
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


# ===== OAuth Queries =====

async def get_or_create_oauth_user(db, provider: str, provider_user_id: str, email: str, full_name: Optional[str]) -> Dict:
    """Get or create user from OAuth provider"""
    # Check if OAuth connection exists
    oauth = await db.db.oauth_providers.find_one({
        "provider": provider,
        "provider_user_id": provider_user_id
    })
    
    if oauth:
        user = await get_user_by_id(db, oauth["user_id"])
        return user
    
    # Check if user exists with this email
    user = await get_user_by_email(db, email)
    
    if not user:
        # Create new user (OAuth users don't have passwords)
        doc = {
            "_id": _new_id(),
            "email": email,
            "password_hash": "",
            "full_name": full_name,
            "age": None,
            "is_verified": True,
            "is_active": True,
            "created_at": _now(),
            "updated_at": _now()
        }
        await db.db.users.insert_one(doc)
        user = dict(doc)
        user["id"] = user.pop("_id")
    
    # Link OAuth provider
    oauth_doc = {
        "_id": _new_id(),
        "user_id": user["id"],
        "provider": provider,
        "provider_user_id": provider_user_id,
        "access_token": None,
        "refresh_token": None,
        "expires_at": None,
        "created_at": _now(),
        "updated_at": _now()
    }
    await db.db.oauth_providers.insert_one(oauth_doc)
    
    return user


async def update_oauth_tokens(db, provider: str, provider_user_id: str, access_token: str, refresh_token: Optional[str], expires_at: Optional[datetime]):
    """Update OAuth provider tokens"""
    await db.db.oauth_providers.update_one(
        {"provider": provider, "provider_user_id": provider_user_id},
        {"$set": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "updated_at": _now()
        }}
    )


# ===== Token Queries =====

async def create_refresh_token(db, user_id, token_hash: str, expires_at: datetime):
    """Store refresh token"""
    doc = {
        "_id": _new_id(),
        "user_id": str(user_id),
        "token_hash": token_hash,
        "token_type": "refresh",
        "expires_at": expires_at,
        "is_revoked": False,
        "created_at": _now(),
        "last_used_at": None
    }
    await db.db.api_tokens.insert_one(doc)


async def get_refresh_token(db, token_hash: str) -> Optional[Dict]:
    """Get refresh token"""
    doc = await db.db.api_tokens.find_one({
        "token_hash": token_hash,
        "token_type": "refresh"
    })
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


async def revoke_token(db, token_hash: str):
    """Revoke a token"""
    await db.db.api_tokens.update_one(
        {"token_hash": token_hash},
        {"$set": {"is_revoked": True}}
    )


async def update_token_last_used(db, token_hash: str):
    """Update last used timestamp"""
    await db.db.api_tokens.update_one(
        {"token_hash": token_hash},
        {"$set": {"last_used_at": _now()}}
    )


# ===== Voice Verification Queries =====

async def create_voice_sample(db, user_id, file_path: str, sample_type: str, audio_duration_ms: int) -> Dict:
    """Store voice sample"""
    doc = {
        "_id": _new_id(),
        "user_id": str(user_id),
        "file_path": file_path,
        "sample_type": sample_type,
        "audio_duration_ms": audio_duration_ms,
        "created_at": _now()
    }
    await db.db.voice_samples.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_voice_samples(db, user_id, sample_type: str = "enrollment") -> List[Dict]:
    """Get user's voice samples"""
    cursor = db.db.voice_samples.find({
        "user_id": str(user_id),
        "sample_type": sample_type
    }).sort("created_at", -1)
    
    results = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        results.append(doc)
    return results


async def count_voice_samples(db, user_id, sample_type: str = "enrollment") -> int:
    """Count user's voice samples"""
    return await db.db.voice_samples.count_documents({
        "user_id": str(user_id),
        "sample_type": sample_type
    })


async def delete_voice_samples(db, user_id):
    """Delete all voice samples for a user"""
    await db.db.voice_samples.delete_many({"user_id": str(user_id)})


async def log_voice_verification(db, user_id, email: str, success: bool, confidence_score: Optional[float], error_message: Optional[str]):
    """Log voice verification attempt"""
    doc = {
        "_id": _new_id(),
        "user_id": str(user_id) if user_id else None,
        "email": email,
        "verification_success": success,
        "confidence_score": confidence_score,
        "error_message": error_message,
        "created_at": _now()
    }
    await db.db.voice_verification_logs.insert_one(doc)


# ===== Session Queries =====

async def create_session(db, user_id, session_type: str) -> Dict:
    """Create a new session"""
    doc = {
        "_id": _new_id(),
        "user_id": str(user_id),
        "session_type": session_type,
        "created_at": _now(),
        "ended_at": None
    }
    await db.db.sessions.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_session(db, session_id) -> Optional[Dict]:
    """Get session by ID"""
    doc = await db.db.sessions.find_one({"_id": str(session_id)})
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


async def get_user_sessions(db, user_id, limit: int = 50) -> List[Dict]:
    """Get user's sessions"""
    cursor = db.db.sessions.find(
        {"user_id": str(user_id)}
    ).sort("created_at", -1).limit(limit)
    
    results = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        results.append(doc)
    return results


async def end_session(db, session_id):
    """End a session"""
    await db.db.sessions.update_one(
        {"_id": str(session_id)},
        {"$set": {"ended_at": _now()}}
    )


# ===== Request Queries =====

async def create_request(db, session_id, user_prompt: str, intent: Optional[str], strategy: Optional[str]) -> Dict:
    """Create a new request"""
    doc = {
        "_id": _new_id(),
        "session_id": str(session_id),
        "user_prompt": user_prompt,
        "intent": intent,
        "strategy": strategy,
        "created_at": _now()
    }
    await db.db.requests.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_request(db, request_id) -> Optional[Dict]:
    """Get request by ID"""
    doc = await db.db.requests.find_one({"_id": str(request_id)})
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


async def get_session_requests(db, session_id) -> List[Dict]:
    """Get all requests in a session"""
    cursor = db.db.requests.find(
        {"session_id": str(session_id)}
    ).sort("created_at", 1)
    
    results = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        results.append(doc)
    return results


# ===== Response Queries =====

async def create_response(db, request_id, final_response: str, models_used: Dict, latency_ms: int, estimated_cost: float) -> Dict:
    """Create a response"""
    doc = {
        "_id": _new_id(),
        "request_id": str(request_id),
        "final_response": final_response,
        "models_used": models_used,
        "latency_ms": latency_ms,
        "estimated_cost": estimated_cost,
        "created_at": _now()
    }
    await db.db.responses.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_response_by_request(db, request_id) -> Optional[Dict]:
    """Get response for a request"""
    doc = await db.db.responses.find_one({"request_id": str(request_id)})
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


# ===== Step Queries =====

async def create_step(db, request_id, step_type: str, model_name: str, input_prompt: str, output_text: str, tokens_used: int, latency_ms: int) -> Dict:
    """Create a request step"""
    doc = {
        "_id": _new_id(),
        "request_id": str(request_id),
        "step_type": step_type,
        "model_name": model_name,
        "input_prompt": input_prompt,
        "output_text": output_text,
        "tokens_used": tokens_used,
        "latency_ms": latency_ms,
        "created_at": _now()
    }
    await db.db.request_steps.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_request_steps(db, request_id) -> List[Dict]:
    """Get all steps for a request"""
    cursor = db.db.request_steps.find(
        {"request_id": str(request_id)}
    ).sort("created_at", 1)
    
    results = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        results.append(doc)
    return results


# ===== OTP Queries =====

async def create_otp(db, email: str, otp_hash: str, expires_at) -> Dict:
    """
    Store a new OTP code (hashed) for an email.
    Invalidates any existing unused OTPs for this email first.
    """
    # Invalidate previous OTPs for this email
    await db.db.otp_codes.update_many(
        {"email": email, "is_used": False},
        {"$set": {"is_used": True}}
    )
    
    doc = {
        "_id": _new_id(),
        "email": email,
        "otp_hash": otp_hash,
        "is_used": False,
        "expires_at": expires_at,
        "created_at": _now()
    }
    await db.db.otp_codes.insert_one(doc)
    result = dict(doc)
    result["id"] = result.pop("_id")
    return result


async def get_valid_otp(db, email: str) -> Optional[Dict]:
    """
    Get the latest valid (unused, unexpired) OTP for an email.
    """
    doc = await db.db.otp_codes.find_one(
        {
            "email": email,
            "is_used": False,
            "expires_at": {"$gt": _now()}
        },
        sort=[("created_at", -1)]
    )
    if not doc:
        return None
    doc["id"] = doc.pop("_id")
    return doc


async def mark_otp_used(db, otp_id: str):
    """Mark an OTP as used/consumed"""
    await db.db.otp_codes.update_one(
        {"_id": otp_id},
        {"$set": {"is_used": True}}
    )


async def mark_user_verified(db, user_id: str):
    """Set is_verified=True on a user"""
    await db.db.users.update_one(
        {"_id": user_id},
        {"$set": {"is_verified": True, "updated_at": _now()}}
    )

