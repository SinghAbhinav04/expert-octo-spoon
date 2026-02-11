from flask import Flask
from asgiref.wsgi import WsgiToAsgi

app = Flask(__name__)

@app.route("/")
def home():
    print("Server started!")
    return "Server is running!"

@app.route("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)

# Wrap for ASGI (required by uvicorn/nixpacks)
asgi_app = WsgiToAsgi(app)
