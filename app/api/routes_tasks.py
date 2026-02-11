from flask import Blueprint, request, jsonify, g
from app.db import models, queries
from app.db.database import db
from app.api import auth
from app.agent.executor import get_agent_runner
import asyncio

bp = Blueprint('tasks', __name__)

# Helper to validate JSON body
def validate_json(model_class):
    data = request.get_json()
    if not data:
        raise ValueError("Missing JSON body")
    return model_class.model_validate(data)

@bp.route("/sessions", methods=["POST"])
@auth.token_required
async def create_session():
    try:
        session_data = validate_json(models.SessionCreate)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400
        
    if not db.client: await db.connect()
    
    session = await queries.create_session(
        db,
        user_id=g.current_user['id'],
        session_type=session_data.session_type.value
    )
    return jsonify(models.SessionResponse(**session).model_dump()), 201

@bp.route("/sessions/<session_id>", methods=["GET"])
@auth.token_required
async def get_session(session_id):
    if not db.client: await db.connect()
    
    session = await queries.get_session(db, session_id)
    if not session:
        return jsonify({"detail": "Session not found"}), 404
        
    if session['user_id'] != g.current_user['id']:
        return jsonify({"detail": "Access denied"}), 403
        
    return jsonify(models.SessionResponse(**session).model_dump())

@bp.route("/sessions", methods=["GET"])
@auth.token_required
async def get_user_sessions():
    limit = request.args.get("limit", 50, type=int)
    if not db.client: await db.connect()
    
    sessions = await queries.get_user_sessions(db, g.current_user['id'], limit)
    return jsonify([models.SessionResponse(**s).model_dump() for s in sessions])

@bp.route("/sessions/<session_id>/end", methods=["POST"])
@auth.token_required
async def end_session(session_id):
    if not db.client: await db.connect()
    
    session = await queries.get_session(db, session_id)
    if not session:
        return jsonify({"detail": "Session not found"}), 404
        
    if session['user_id'] != g.current_user['id']:
        return jsonify({"detail": "Access denied"}), 403
        
    await queries.end_session(db, session_id)
    return jsonify({"message": "Session ended successfully"})

@bp.route("/sessions/<session_id>/requests", methods=["POST"])
@auth.token_required
async def submit_request(session_id):
    try:
        request_data = validate_json(models.RequestCreate)
    except Exception as e:
        return jsonify({"detail": str(e)}), 400
        
    if not db.client: await db.connect()
    
    session = await queries.get_session(db, session_id)
    if not session:
        return jsonify({"detail": "Session not found"}), 404
        
    if session['user_id'] != g.current_user['id']:
        return jsonify({"detail": "Access denied"}), 403
        
    # Route through the agent runner (uses tools, planner, memory)
    runner = get_agent_runner()
    result = await runner.run(
        db=db,
        session_id=session_id,
        user_id=g.current_user['id'],
        user_prompt=request_data.user_prompt,
    )
    return jsonify(result.to_dict())

@bp.route("/requests/<request_id>", methods=["GET"])
@auth.token_required
async def get_request_endpoint(request_id):
    if not db.client: await db.connect()
    
    req = await queries.get_request(db, request_id)
    if not req:
        return jsonify({"detail": "Request not found"}), 404
        
    session = await queries.get_session(db, req['session_id'])
    if session['user_id'] != g.current_user['id']:
        return jsonify({"detail": "Access denied"}), 403
        
    return jsonify(models.RequestResponse(**req).model_dump())

@bp.route("/requests/<request_id>/steps", methods=["GET"])
@auth.token_required
async def get_request_steps(request_id):
    if not db.client: await db.connect()
    
    req = await queries.get_request(db, request_id)
    if not req:
        return jsonify({"detail": "Request not found"}), 404
        
    session = await queries.get_session(db, req['session_id'])
    if session['user_id'] != g.current_user['id']:
        return jsonify({"detail": "Access denied"}), 403
        
    steps = await queries.get_request_steps(db, request_id)
    return jsonify([models.StepResponse(**step).model_dump() for step in steps])

@bp.route("/requests/<request_id>/response", methods=["GET"])
@auth.token_required
async def get_request_response(request_id):
    if not db.client: await db.connect()
    
    req = await queries.get_request(db, request_id)
    if not req:
        return jsonify({"detail": "Request not found"}), 404
        
    session = await queries.get_session(db, req['session_id'])
    if session['user_id'] != g.current_user['id']:
        return jsonify({"detail": "Access denied"}), 403
        
    response = await queries.get_response_by_request(db, request_id)
    if not response:
        return jsonify({"detail": "Response not found"}), 404
        
    return jsonify(models.FinalResponse(**response).model_dump())
