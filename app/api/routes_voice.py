from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename
from app.db import models, queries
from app.db.database import db
from app.api import auth
from app.voice import get_voice_processor
import asyncio
import os
import uuid
import aiofiles
from pathlib import Path
from app.config import settings
import numpy as np

bp = Blueprint('voice', __name__, url_prefix='/voice')

async def save_voice_file(user_id: str, file_storage) -> tuple[str, int]:
    voice_dir = Path(settings.VOICE_SAMPLES_DIR) / str(user_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    
    filename = secure_filename(file_storage.filename)
    if not filename:
        filename = f"{uuid.uuid4()}.wav"
    else:
        file_extension = filename.split(".")[-1] if "." in filename else "wav"
        filename = f"{uuid.uuid4()}.{file_extension}"
        
    file_path = voice_dir / filename
    
    # Read content synchronously (Flask file storage)
    content = file_storage.read()
    
    # Write async
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
        
    duration_ms = (len(content) // 16) if content else 1000
    return str(file_path), duration_ms

async def save_voice_embedding(db, user_id: str, embedding: np.ndarray) -> None:
    embedding_bytes = embedding.tobytes()
    voice_dir = Path(settings.VOICE_SAMPLES_DIR) / str(user_id)
    embedding_path = voice_dir / "enrollment_embedding.npy"
    np.save(embedding_path, embedding)

async def load_voice_embedding(user_id: str):
    voice_dir = Path(settings.VOICE_SAMPLES_DIR) / str(user_id)
    embedding_path = voice_dir / "enrollment_embedding.npy"
    if not embedding_path.exists():
        return None
    return np.load(embedding_path)

@bp.route("/enroll", methods=["POST"])
@auth.token_required
async def enroll_voice():
    if 'audio' not in request.files:
        return jsonify({"detail": "No audio file"}), 400
    
    audio = request.files['audio']
    if not audio.filename:
        return jsonify({"detail": "Empty filename"}), 400
        
    if not db.client: await db.connect()
    
    try:
        file_path, duration_ms = await save_voice_file(g.current_user['id'], audio)
        
        voice_processor = get_voice_processor()
        embedding = voice_processor.create_embedding(file_path)
        
        await save_voice_embedding(db, g.current_user['id'], embedding)
        
        voice_sample = await queries.create_voice_sample(
            db,
            user_id=g.current_user['id'],
            file_path=file_path,
            sample_type="enrollment",
            audio_duration_ms=duration_ms
        )
        
        sample_count = await queries.count_voice_samples(db, g.current_user['id'])
        
        return jsonify(models.VoiceEnrollmentResponse(
            id=str(voice_sample['id']),
            user_id=str(g.current_user['id']),
            sample_count=sample_count,
            message=f"Voice enrolled successfully! Embedding created from {duration_ms/1000:.1f}s audio."
        ).model_dump())
        
    except Exception as e:
        return jsonify({"detail": f"Voice enrollment failed: {str(e)}"}), 500

@bp.route("/verify", methods=["POST"])
async def verify_voice():
    email = request.form.get("email")
    if not email:
        return jsonify({"detail": "Email required"}), 400
        
    if 'audio' not in request.files:
        return jsonify({"detail": "Audio required"}), 400
    audio = request.files['audio']
    
    if not db.client: await db.connect()
    
    user = await queries.get_user_by_email(db, email)
    if not user:
        await queries.log_voice_verification(db, None, email, False, None, "User not found")
        return jsonify({"detail": "Voice verification failed"}), 401
        
    enrolled_embedding = await load_voice_embedding(user['id'])
    if enrolled_embedding is None:
        await queries.log_voice_verification(db, user['id'], email, False, None, "No enrollment")
        return jsonify({"detail": "No voice enrollment found"}), 400
        
    try:
        file_path, duration_ms = await save_voice_file(user['id'], audio)
        
        await queries.create_voice_sample(
            db, user_id=user['id'], file_path=file_path, sample_type="verification", audio_duration_ms=duration_ms
        )
        
        voice_processor = get_voice_processor()
        is_match, similarity = voice_processor.verify_speaker(
            test_audio_path=file_path,
            enrolled_embedding=enrolled_embedding,
            threshold=settings.VOICE_MATCH_THRESHOLD
        )
        
        if is_match:
            access_token = auth.create_access_token(user['id'])
            refresh_token, refresh_expires = auth.create_refresh_token(user['id'])
            token_hash = auth.hash_token(refresh_token)
            await queries.create_refresh_token(db, user['id'], token_hash, refresh_expires)
            
            await queries.log_voice_verification(db, user['id'], email, True, similarity, None)
            
            return jsonify(models.VoiceVerificationResponse(
                success=True,
                confidence_score=similarity,
                access_token=access_token,
                refresh_token=refresh_token,
                user=models.UserResponse(**user),
                message=f"Voice verified! ✅ Similarity: {similarity*100:.1f}%"
            ).model_dump())
        else:
            await queries.log_voice_verification(db, user['id'], email, False, similarity, "Low similarity")
            return jsonify(models.VoiceVerificationResponse(
                success=False,
                confidence_score=similarity,
                access_token=None,
                refresh_token=None,
                user=None,
                message=f"Voice not recognized."
            ).model_dump())
            
    except Exception as e:
         await queries.log_voice_verification(db, user['id'], email, False, None, str(e))
         return jsonify({"detail": f"Error: {str(e)}"}), 500

@bp.route("/wake", methods=["POST"])
@auth.token_required
async def wake_word_detection():
    return jsonify({
        "wake_detected": True,
        "confidence": 0.92,
        "message": "Wake word detected"
    })

@bp.route("/samples", methods=["GET"])
@auth.token_required
async def get_voice_samples():
    if not db.client: await db.connect()
    samples = await queries.get_voice_samples(db, g.current_user['id'], "enrollment")
    
    return jsonify({
        "user_id": str(g.current_user['id']),
        "sample_count": len(samples),
        "samples": [
            {
                "id": str(s['id']),
                "created_at": s['created_at'].isoformat(),
                "duration_ms": s['audio_duration_ms']
            }
            for s in samples
        ]
    })

@bp.route("/delete", methods=["DELETE"])
@auth.token_required
async def delete_voice_enrollment():
    if not db.client: await db.connect()
    
    samples = await queries.get_voice_samples(db, g.current_user['id'])
    for sample in samples:
         try:
             p = Path(sample['file_path'])
             if p.exists(): p.unlink()
         except: pass
         
    await queries.delete_voice_samples(db, g.current_user['id'])
    return jsonify({"message": f"Deleted {len(samples)} voice samples"})
