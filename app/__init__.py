from flask import Flask
from app.routes.agent_routes import agent_bp
from app.routes.langgraph_routes import graph_bp
from app.routes.query_routes import query_bp

def create_app():
    app = Flask(__name__)

    # 블루프린트 등록
    app.register_blueprint(agent_bp)
    app.register_blueprint(graph_bp)
    app.register_blueprint(query_bp)

    return app