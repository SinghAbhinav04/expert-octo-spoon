from flask import Blueprint, request, jsonify, redirect
from app.api import auth
from app.db import queries, models
from app.db.database import db
from app.config import settings
from app.services.email_service import generate_otp, hash_otp, get_otp_expiry, send_otp_email, send_login_alert_email
import httpx

bp = Blueprint('auth', __name__, url_prefix='/auth')

# Helper to validate JSON body
def validate_json(model_class):
    data = request.get_json()
    if not data:
        raise ValueError("Missing JSON body")
    return model_class.model_validate(data)

@bp.route("/signup", methods=["POST"])
async def signup():
    try:
        user_data = validate_json(models.UserCreate)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400

    # Ensure DB
    if not db.client: await db.connect()
    
    existing_user = await queries.get_user_by_email(db, user_data.email)
    if existing_user:
        return jsonify({"detail": "Email already registered"}), 400
    
    password_hash = auth.hash_password(user_data.password)
    user = await queries.create_user(
        db,
        email=user_data.email,
        password_hash=password_hash,
        full_name=user_data.full_name,
        age=user_data.age
    )
    
    otp_code = generate_otp()
    otp_hash = hash_otp(otp_code)
    expires_at = get_otp_expiry()
    
    await queries.create_otp(db, email=user_data.email, otp_hash=otp_hash, expires_at=expires_at)
    send_otp_email(user_data.email, otp_code, action="signup")
    
    response = models.OTPResponse(
        message="Account created! Check your email for the verification code.",
        email=user_data.email,
        requires_otp=True,
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES
    )
    return jsonify(response.model_dump()), 201

@bp.route("/login", methods=["POST"])
async def login():
    try:
        credentials = validate_json(models.UserLogin)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400

    if not db.client: await db.connect()

    user = await auth.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        return jsonify({"detail": "Incorrect email or password"}), 401
    
    otp_code = generate_otp()
    otp_hash = hash_otp(otp_code)
    expires_at = get_otp_expiry()
    
    await queries.create_otp(db, email=credentials.email, otp_hash=otp_hash, expires_at=expires_at)
    send_otp_email(credentials.email, otp_code, action="login")
    
    response = models.OTPResponse(
        message="Credentials verified! Check your email for the verification code.",
        email=credentials.email,
        requires_otp=True,
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES
    )
    return jsonify(response.model_dump())

@bp.route("/verify-otp", methods=["POST"])
async def verify_otp():
    try:
        data = validate_json(models.OTPVerify)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400

    if not db.client: await db.connect()

    stored_otp = await queries.get_valid_otp(db, data.email)
    if not stored_otp:
        return jsonify({"detail": "OTP expired or not found. Please request a new code."}), 400
    
    if hash_otp(data.otp_code) != stored_otp["otp_hash"]:
        return jsonify({"detail": "Invalid OTP code"}), 401
    
    await queries.mark_otp_used(db, stored_otp["id"])
    
    user = await queries.get_user_by_email(db, data.email)
    if not user:
        return jsonify({"detail": "User not found"}), 404
    
    await queries.mark_user_verified(db, user["id"])
    
    access_token = auth.create_access_token(user["id"])
    refresh_token, refresh_expires = auth.create_refresh_token(user["id"])
    
    token_hash = auth.hash_token(refresh_token)
    await queries.create_refresh_token(db, user["id"], token_hash, refresh_expires)
    
    # Send login alert
    client_ip = request.headers.get("x-forwarded-for", request.remote_addr or "unknown")
    user_agent = request.headers.get("user-agent", "Unknown")
    send_login_alert_email(data.email, client_ip, user_agent)
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    })

@bp.route("/resend-otp", methods=["POST"])
async def resend_otp():
    try:
        data = validate_json(models.OTPRequest)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400

    if not db.client: await db.connect()

    user = await queries.get_user_by_email(db, data.email)
    if not user:
        return jsonify({"detail": "No account found with this email"}), 404
    
    otp_code = generate_otp()
    otp_hash = hash_otp(otp_code)
    expires_at = get_otp_expiry()
    
    await queries.create_otp(db, email=data.email, otp_hash=otp_hash, expires_at=expires_at)
    send_otp_email(data.email, otp_code, action="verify")
    
    response = models.OTPResponse(
        message="New verification code sent to your email.",
        email=data.email,
        requires_otp=True,
        expires_in_minutes=settings.OTP_EXPIRE_MINUTES
    )
    return jsonify(response.model_dump())

@bp.route("/refresh", methods=["POST"])
async def refresh_access_token():
    try:
        data = validate_json(models.RefreshTokenRequest)
    except Exception as e:
         return jsonify({"detail": str(e)}), 400
         
    try:
        payload = auth.decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            return jsonify({"detail": "Invalid token type"}), 401
        user_id = payload.get("sub")
    except Exception:
        return jsonify({"detail": "Invalid refresh token"}), 401
    
    if not db.client: await db.connect()
    
    token_hash = auth.hash_token(data.refresh_token)
    stored_token = await queries.get_refresh_token(db, token_hash)
    
    if not stored_token or stored_token['is_revoked']:
        return jsonify({"detail": "Invalid or revoked refresh token"}), 401
    
    await queries.update_token_last_used(db, token_hash)
    access_token = auth.create_access_token(user_id)
    
    return jsonify({"access_token": access_token, "token_type": "bearer"})

@bp.route("/logout", methods=["POST"])
@auth.token_required
async def logout():
    try:
        data = validate_json(models.RefreshTokenRequest)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400
        
    if not db.client: await db.connect()
    token_hash = auth.hash_token(data.refresh_token)
    await queries.revoke_token(db, token_hash)
    
    return jsonify({"message": "Successfully logged out"})

@bp.route("/oauth/google", methods=["GET"])
async def google_oauth_redirect():
    if not settings.GOOGLE_CLIENT_ID:
        return jsonify({"detail": "Google OAuth not configured"}), 501
    
    oauth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={settings.GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile&"
        f"access_type=offline"
    )
    return redirect(oauth_url)

@bp.route("/oauth/google/callback", methods=["GET"])
async def google_oauth_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"detail": "Missing code"}), 400
        
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
        if token_response.status_code != 200:
            return jsonify({"detail": "Failed to exchange code for token"}), 400
        
        tokens = token_response.json()
        google_access_token = tokens["access_token"]
    
    user_info = await auth.get_google_user_info(google_access_token)
    
    if not db.client: await db.connect()
    user = await queries.get_or_create_oauth_user(
        db,
        provider="google",
        provider_user_id=user_info["id"],
        email=user_info["email"],
        full_name=user_info.get("name")
    )
    
    await queries.update_oauth_tokens(
        db,
        provider="google",
        provider_user_id=user_info["id"],
        access_token=google_access_token,
        refresh_token=tokens.get("refresh_token"),
        expires_at=None
    )
    
    access_token = auth.create_access_token(user['id'])
    refresh_token, refresh_expires = auth.create_refresh_token(user['id'])
    token_hash = auth.hash_token(refresh_token)
    await queries.create_refresh_token(db, user['id'], token_hash, refresh_expires)
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": models.UserResponse(**user).model_dump()
    })

@bp.route("/oauth/github", methods=["GET"])
async def github_oauth_redirect():
    if not settings.GITHUB_CLIENT_ID:
        return jsonify({"detail": "GitHub OAuth not configured"}), 501
    
    oauth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={settings.GITHUB_CLIENT_ID}&"
        f"redirect_uri={settings.GITHUB_REDIRECT_URI}&"
        f"scope=user:email"
    )
    return redirect(oauth_url)

@bp.route("/oauth/github/callback", methods=["GET"])
async def github_oauth_callback():
    code = request.args.get("code")
    if not code:
         return jsonify({"detail": "Missing code"}), 400
         
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "code": code,
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "redirect_uri": settings.GITHUB_REDIRECT_URI
            },
            headers={"Accept": "application/json"}
        )
        if token_response.status_code != 200:
             return jsonify({"detail": "Failed to exchange code for token"}), 400
        
        tokens = token_response.json()
        github_access_token = tokens["access_token"]
        
    user_info = await auth.get_github_user_info(github_access_token)
    if not user_info.get("email"):
        return jsonify({"detail": "Email not available from GitHub"}), 400
        
    if not db.client: await db.connect()
    user = await queries.get_or_create_oauth_user(
        db,
        provider="github",
        provider_user_id=str(user_info["id"]),
        email=user_info["email"],
        full_name=user_info.get("name")
    )
    
    await queries.update_oauth_tokens(
        db,
        provider="github",
        provider_user_id=str(user_info["id"]),
        access_token=github_access_token,
        refresh_token=None,
        expires_at=None
    )
    
    access_token = auth.create_access_token(user['id'])
    refresh_token, refresh_expires = auth.create_refresh_token(user['id'])
    token_hash = auth.hash_token(refresh_token)
    await queries.create_refresh_token(db, user['id'], token_hash, refresh_expires)
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": models.UserResponse(**user).model_dump()
    })

@bp.route("/me", methods=["GET"])
@auth.token_required
async def get_current_user_info():
    from flask import g
    return jsonify(models.UserResponse(**g.current_user).model_dump())
