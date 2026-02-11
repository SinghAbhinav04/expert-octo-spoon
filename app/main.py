from flask import Flask, jsonify
from flask_cors import CORS
from asgiref.wsgi import WsgiToAsgi
from app.config import settings
from app.db.database import db

app = Flask(__name__)
# Enable CORS
CORS(app)

@app.route("/")
async def home():
    return jsonify({
        "message": "Step 4: Full App",
        "version": settings.APP_VERSION,
        "status": "running"
    })

@app.route("/health")
async def health():
    if not db.client:
        await db.connect()
    
    try:
        await db.client.admin.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "database": str(e)}), 500

# Blueprints
from app.api.routes_auth import bp as auth_bp
from app.api.routes_tasks import bp as tasks_bp
from app.api.routes_agent import bp as agent_bp
# from app.api.routes_voice import bp as voice_bp  <-- Disabled to avoid missing deps

app.register_blueprint(auth_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(agent_bp)
# app.register_blueprint(voice_bp)

# WsgiToAsgi wrapper for Uvicorn
asgi_app = WsgiToAsgi(app)
