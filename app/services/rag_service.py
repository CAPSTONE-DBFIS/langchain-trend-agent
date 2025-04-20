from typing import List
import fitz
import docx
import olefile
import re
from fastapi import UploadFile
from io import BytesIO
from app.utils.milvus_util import get_team_file_vector_store, get_embedding_model, get_personal_file_vector_store
from app.utils.hwp_parser import extract_text_from_hwp_binary
from typing import Literal
from pymilvus import Collection

async def save_file_to_milvus(
        mode: Literal["team", "personal"],
        file: UploadFile,
        uploader_id: str,
        team_id: int = None
):
    """
    업로드된 파일을 Milvus에 저장 (팀 또는 개인)

    - mode: 'team' 또는 'personal'
    - uploader_id: 업로더 ID
    - team_id: 팀 파일일 경우 필수
    """
    filename = file.filename.lower()
    basename = file.filename.lower().rsplit("/", 1)[-1]
    contents = await file.read()

    # 텍스트 추출
    if filename.endswith(".pdf"):
        text = extract_pdf(contents)
    elif filename.endswith(".docx"):
        text = extract_docx(contents)
    elif filename.endswith(".hwp"):
        text = extract_hwp(contents)
    else:
        raise Exception("지원하지 않는 파일 형식입니다.")

    # 문장 분할 + 임베딩
    chunks = split_text(text)
    embeddings = embed_chunks(chunks)

    # 벡터 스토어 선택
    if mode == "team":
        if team_id is None:
            raise ValueError("팀 파일 저장 시 team_id는 필수입니다.")
        vector_store = get_team_file_vector_store()
    elif mode == "personal":
        vector_store = get_personal_file_vector_store()
    else:
        raise ValueError("mode는 'team' 또는 'personal'이어야 합니다.")


    # 메타데이터 생성
    metadatas = []
    for chunk in chunks:
        meta = {
            "content": chunk,
            "filename": basename,
            "uploader_id": uploader_id
        }
        if mode == "team":
            meta["team_id"] = team_id
        metadatas.append(meta)

    # Milvus에 저장
    vector_store.add_embeddings(
        texts=chunks,
        embeddings=embeddings,
        metadatas=metadatas
    )

def extract_pdf(contents: bytes) -> str:
    """PDF 파일의 내용을 텍스트로 추출합니다."""
    text = ""
    with fitz.open(stream=contents, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text("text")  # 성능 가장 좋은 방식
    return text.strip()


def extract_docx(contents: bytes) -> str:
    """DOCX 파일에서 텍스트 추출"""
    doc = docx.Document(BytesIO(contents))
    return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])


def extract_hwp(contents: bytes) -> str:
    """
    HWP 텍스트 추출 (OLE 기반)
    """
    buffer = BytesIO(contents)
    if not olefile.isOleFile(buffer):
        raise ValueError("올바르지 않은 HWP 파일입니다.")
    buffer.seek(0)
    return extract_text_from_hwp_binary(buffer.read())


def split_text(text: str, max_len: int = 2000) -> List[str]:
    """문장을 단위로 나누고 길이 제한에 따라 잘라주는 함수"""
    sentences = re.split(r'[\.!?\n]', text)
    chunks = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) < max_len:
            current += sentence + " "
        else:
            chunks.append(current.strip())
            current = sentence + " "
    if current:
        chunks.append(current.strip())
    return chunks


def embed_chunks(chunks: List[str]) -> List[List[float]]:
    """HuggingFace SBERT 임베딩"""
    embedding_model = get_embedding_model()  # snunlp/KR-SBERT-V40K-klueNLI-augSTS
    return embedding_model.embed_documents(chunks)


def delete_team_embedding(team_id: int, filename: str) -> int:
    """팀 파일 컬렉션에서 파일을 삭제"""
    filename = filename.lower()
    expr = f'filename == "{filename}" and team_id == {team_id}'
    collection = Collection("team_shared_files")
    result = collection.delete(expr)
    return result.delete_count

#
# from app.utils.milvus_util import connect_milvus
# from pymilvus import Collection
#
# connect_milvus()
# collection = Collection("team_shared_files")
#
# # ✅ 전체 데이터 보기 (빈 expr 금지 → 최소 조건 줘야 함)
# all_data = collection.query(expr="team_id >= 0", output_fields=["filename", "team_id"])
# print("[DEBUG] 전체 데이터:")
# for row in all_data:
#     print(row)
#
# # 삭제 조건 설정
# filename = "in_class_activity_2_2019040519.pdf"
# team_id = 30
# expr = f'filename == "{filename}" and team_id == {team_id}'
#
# print(f"[DEBUG] expr = {expr}")
#
# # 삭제 대상 확인
# data = collection.query(expr=expr, output_fields=["filename", "team_id"])
# print("[DEBUG] 삭제 대상 사전 조회:")
# print(data)
#
# # 삭제 실행
# result = collection.delete(expr)
# print(f"[DEBUG] 삭제 결과: {result.delete_count}")