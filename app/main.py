from typing import List

from fastapi import UploadFile, File, Form

from app.services.agent_service import AgentChatService
from app.services.team_file_rag_service import TeamFileRAGService
from app.services.team_file_ops_service import TeamFileOpsService
from app.utils.file_util import save_upload_file_to_disk

import logging
from fastapi import FastAPI
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

@app.post("/agent/query")
async def agent_query(
    query: str = Form(...),
    chat_room_id: int = Form(...),
    member_id: str = Form(...),
    persona_id: int = Form(None),
    model_type: str = Form("gpt-4o-mini"),
    files: List[UploadFile] = File(None)
):
    print(model_type)
    file_statuses = None

    if files:
        file_statuses = []
        for file in files:
            try:
                await save_upload_file_to_disk(file, member_id)
                file_statuses.append({
                    "status": "success",
                    "filename": file.filename,
                    "uploader": member_id
                })
            except Exception as e:
                file_statuses.append({
                    "status": "error",
                    "filename": file.filename,
                    "error": str(e)
                })

    return await AgentChatService.stream_response( query, chat_room_id, member_id, persona_id, file_statuses, model_type)


@app.post("/team-files")
async def upload_team_file(
    team_id: str = Form(...),
    file_id: str = Form(...),
    file: UploadFile = File(...)
):
    print("수신된 파일 이름:", file.filename)
    return await TeamFileOpsService.upload(team_id, file_id, file)


@app.delete("/team-files/{team_id}/{file_id}")
async def delete_team_file(
    team_id: str,
    file_id: str,
):
    TeamFileOpsService.delete(team_id, file_id)
    return {"status": "ok", "message": "벡터 임베딩 삭제 완료"}



@app.post("/team-file/query")
async def team_file_query(
    team_id: str = Form(...),
    query: str = Form(...),
):
    return await TeamFileRAGService.stream_team_file_response(team_id, query)