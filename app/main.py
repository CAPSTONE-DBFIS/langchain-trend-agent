from typing import List

from fastapi import UploadFile, File, Form
from app.services.agent_service import AgentChatService
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
    model_type: str = Form("claude"),
    files: List[UploadFile] = File(None)
):

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