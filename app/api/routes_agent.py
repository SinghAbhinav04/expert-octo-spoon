"""
Agent API routes — Agentic endpoints for minimal.ai

Endpoints:
- POST /agent/run          Submit a task to the agent
- GET  /agent/plan/<id>    Get the execution plan for a request
- GET  /agent/steps/<id>   Get step-by-step execution details
- GET  /agent/tools        List all registered tools
- GET  /agent/memory/<sid> Get session memory/context
"""
from flask import Blueprint, request, jsonify, g
from app.db import models, queries
from app.db.database import db
from app.api import auth
from app.agent.executor import get_agent_runner
from app.agent.tool_registry import get_tool_registry
from app.agent.memory import get_memory_manager

bp = Blueprint("agent", __name__, url_prefix="/agent")


@bp.route("/run", methods=["POST"])
@auth.token_required
async def agent_run():
    """
    Submit a task to the autonomous agent.
    
    Body: {"prompt": "your task here"}
    Returns: agent result with response, plan, and steps
    """
    data = request.get_json()
    if not data or not data.get("prompt"):
        return jsonify({"detail": "Missing 'prompt' in request body"}), 400

    user_prompt = data["prompt"]
    if len(user_prompt) > 5000:
        return jsonify({"detail": "Prompt too long (max 5000 chars)"}), 400

    # Session ID: use provided or create a new one
    session_id = data.get("session_id")

    if not db.client:
        await db.connect()

    if not session_id:
        # Auto-create a session
        session = await queries.create_session(
            db,
            user_id=g.current_user["id"],
            session_type="agent",
        )
        session_id = session["id"]
    else:
        # Verify session ownership
        session = await queries.get_session(db, session_id)
        if not session:
            return jsonify({"detail": "Session not found"}), 404
        if session["user_id"] != g.current_user["id"]:
            return jsonify({"detail": "Access denied"}), 403

    # Run the agent
    runner = get_agent_runner()
    result = await runner.run(
        db=db,
        session_id=session_id,
        user_id=g.current_user["id"],
        user_prompt=user_prompt,
    )

    response = result.to_dict()
    response["session_id"] = session_id
    return jsonify(response)


@bp.route("/plan/<request_id>", methods=["GET"])
@auth.token_required
async def get_plan(request_id):
    """Get the execution plan for a specific request"""
    if not db.client:
        await db.connect()

    plan = await queries.get_agent_plan(db, request_id)
    if not plan:
        return jsonify({"detail": "Plan not found"}), 404

    # Verify ownership via request -> session -> user
    req = await queries.get_request(db, request_id)
    if req:
        session = await queries.get_session(db, req["session_id"])
        if session and session["user_id"] != g.current_user["id"]:
            return jsonify({"detail": "Access denied"}), 403

    return jsonify(plan)


@bp.route("/steps/<request_id>", methods=["GET"])
@auth.token_required
async def get_steps(request_id):
    """Get step-by-step execution details for a request"""
    if not db.client:
        await db.connect()

    # Verify ownership
    req = await queries.get_request(db, request_id)
    if not req:
        return jsonify({"detail": "Request not found"}), 404

    session = await queries.get_session(db, req["session_id"])
    if session["user_id"] != g.current_user["id"]:
        return jsonify({"detail": "Access denied"}), 403

    steps = await queries.get_request_steps(db, request_id)
    return jsonify([models.StepResponse(**step).model_dump() for step in steps])


@bp.route("/tools", methods=["GET"])
@auth.token_required
async def list_tools():
    """List all registered agent tools"""
    registry = get_tool_registry()
    return jsonify({
        "tools": registry.list_tools(),
        "count": registry.count(),
    })


@bp.route("/memory/<session_id>", methods=["GET"])
@auth.token_required
async def get_memory(session_id):
    """Get session memory/conversation history"""
    if not db.client:
        await db.connect()

    # Verify session ownership
    session = await queries.get_session(db, session_id)
    if not session:
        return jsonify({"detail": "Session not found"}), 404
    if session["user_id"] != g.current_user["id"]:
        return jsonify({"detail": "Access denied"}), 403

    memory = get_memory_manager()
    entries = await memory.get_session_memory(db, session_id)

    return jsonify({
        "session_id": session_id,
        "entries": [
            {
                "id": e.get("id", ""),
                "prompt": e.get("prompt", ""),
                "response": e.get("response", "")[:500],
                "plan_summary": e.get("plan_summary"),
                "created_at": e.get("created_at", "").isoformat() if hasattr(e.get("created_at", ""), "isoformat") else str(e.get("created_at", "")),
            }
            for e in entries
        ],
        "count": len(entries),
    })
