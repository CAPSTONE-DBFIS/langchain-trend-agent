from flask import Flask
from app.routes.query_routes import query_bp

def create_app():
    """Flask 애플리케이션 인스턴스 생성 및 설정"""
    app = Flask(__name__)

    # 블루프린트 등록
    app.register_blueprint(query_bp)

    return app