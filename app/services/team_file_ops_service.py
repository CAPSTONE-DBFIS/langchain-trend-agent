from fastapi import UploadFile
from app.utils.team_file_util import extract_text_from_uploadfile, chunk_text
from app.utils.milvus_util import get_team_file_vector_store
import logging

logger = logging.getLogger(__name__)

class TeamFileOpsService:
    def __init__(self):
        self.vector_store = get_team_file_vector_store()

    @staticmethod
    async def upload(team_id: str, file_id: str, file: UploadFile) -> dict:
        """
        Milvus에 해당 파일의 임베딩을 team_id, file_id, file_name 메타데이터와 함께 저장
        """
        try:
            # 업로드 파일 텍스트 추출
            text = await extract_text_from_uploadfile(file)
            chunks = chunk_text(text)
            file_name = file.filename

            # Milvus에 저장
            vector_store = get_team_file_vector_store()
            metadatas = [{"team_id": str(team_id), "file_id": str(file_id), "file_name": file_name} for _ in chunks]
            vector_store.add_texts(texts=chunks, metadatas=metadatas)

            return {
                "status": "ok",
                "inserted": len(chunks),
                "file_name": file_name,
            }

        except Exception as e:
            logger.error(f"업로드 실패: {e}")
            return {"status": "error", "reason": str(e)}

    @staticmethod
    def delete(team_id: str, file_id: str):
        """
        Milvus에서 해당 파일 ID의 벡터 임베딩 삭제
        """
        expr = f'team_id == "{team_id}" and file_id == "{file_id}"'
        vector_store = get_team_file_vector_store()
        vector_store.delete(expr=expr)
        logger.info("벡터 삭제 완료 - team_id={team_id}, file_id={file_id}")