from flask import Blueprint, request, jsonify
from app.services.query_service import process_user_query

query_bp = Blueprint('query', __name__)

@query_bp.route('/query', methods=['POST'])
def handle_query():
    try:
        # 요청 본문을 JSON으로 파싱
        data = request.get_json()

        # 요청 데이터 유효성 검사
        if not data or 'query' not in data:
            return jsonify({"error": "쿼리가 필요합니다."}), 400

        query = data['query'].strip()
        session_id = data.get('session_id', 'default_session')  # 세션 ID 기본값 설정

        if not query:
            return jsonify({"error": "빈 쿼리는 허용되지 않습니다."}), 400

        # 쿼리 처리
        results = process_user_query(session_id, query)  # session_id 추가

        # 응답을 UTF-8 인코딩
        response = jsonify({"results": results})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response

    except Exception as e:
        return jsonify({"error": "서버 내부 오류 발생", "details": str(e)}), 500