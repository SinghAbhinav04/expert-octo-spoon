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
        "message": "Step 2: Config + DB",
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

# WsgiToAsgi wrapper for Uvicorn
asgi_app = WsgiToAsgi(app)
