from flask import Blueprint, request, jsonify
from app.services.langgraph_service import run_search_workflow

graph_bp = Blueprint('graph', __name__)

@graph_bp.route('/graph/query', methods=['POST'])
async def query_agent():
    """
    Spring 서버에서 요청을 보내면 Flask가 LangGraph를 통한 에이전트를 실행해 응답을 반환하는 API
    """
    try:
        # JSON 요청 파싱
        data = request.json
        user_query = data.get("query")
        chat_room_id = str(data.get("chat_room_id"))  # 명시적으로 str 변환
        member_id = str(data.get("member_id"))  # 명시적으로 str 변환

        if not user_query or not chat_room_id or not member_id:
            return jsonify({"error": "Missing required parameters"}), 400

        print(f"Flask received request: query={user_query}, chat_room_id={chat_room_id}, member_id={member_id}")

        # LangChain 서비스 호출 (비동기 실행)
        response = await run_search_workflow(user_query, chat_room_id, member_id)

        print(f"LangChain Response: {response}")

        return jsonify({
            "query": user_query,
            "gpt_response": response
        })

    except Exception as e:
        print(f"Flask Error: {str(e)}")
        return jsonify({"error": str(e)}), 500