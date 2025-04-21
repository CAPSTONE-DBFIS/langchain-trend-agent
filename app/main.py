from fastapi import UploadFile, File, Form

from app.services.agent_service import AgentChatService
from app.services.deep_research_service import get_streaming_response
from app.services.rag_service import save_file_to_milvus, delete_team_embedding
from app.utils.milvus_util import connect_milvus
import logging
from fastapi import FastAPI, Request
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

connect_milvus()

@app.post("/agent/query")
async def agent_query(request: Request):
    body = await request.json()
    query = body.get("query")
    chat_room_id = body.get("chat_room_id")
    member_id = body.get("member_id")

    return await AgentChatService.stream_response(query, chat_room_id, member_id)

@app.post("/research/multi/stream")
async def stream_research(request: Request):
    body = await request.json()
    topic = body.get("topic")
    if not topic:
        return {"error": "topic is required"}
    return get_streaming_response(topic)


@app.post("/rag/team")
async def rag_upload(
        file: UploadFile = File(...),
        team_id: int = Form(...),
        uploader_id: str = Form(...)
):
    """팀 파일을 Milvus에 저장"""
    try:
        await save_file_to_milvus("team", file, uploader_id, team_id)
        logger.info(f"팀 파일 저장 완료: team_id={team_id}, uploader_id={uploader_id}, filename={file.filename}")
        return {"message": "팀 파일 RAG 저장 완료"}
    except Exception as e:
        logger.error(f"팀 파일 저장 실패: {str(e)}")
        return {"error": str(e)}


@app.delete("/rag/team")
async def delete_team_file_from_milvus(team_id: int, filename: str):
    """팀 파일을 Milvus에서 삭제"""
    try:
        deleted_count = delete_team_embedding(team_id, filename)
        logger.info(f"팀 파일 삭제 완료: team_id={team_id}, filename={filename}, 삭제된 수={deleted_count}")
        return {"deleted": deleted_count}
    except Exception as e:
        logger.error(f"팀 파일 삭제 실패: {str(e)}")
        return {"error": str(e)}

@app.post("/rag/personal")
async def upload_user_file(
        file: UploadFile = File(...),
        user_id: str = Form(...)
):
    """개인 파일을 Milvus에 저장"""
    try:
        await save_file_to_milvus("personal", file, user_id)
        logger.info(f"개인 파일 저장 완료: user_id={user_id}, filename={file.filename}")
        return {"message": "개인 파일 RAG 저장 완료"}
    except Exception as e:
        logger.error(f"개인 파일 저장 실패: {str(e)}")
        return {"error": str(e)}