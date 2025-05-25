import tempfile
import os
import fitz
import docx
from fastapi import UploadFile
from langchain.text_splitter import RecursiveCharacterTextSplitter

async def extract_text_from_uploadfile(file: UploadFile) -> str:
    """업로드된 파일에서 텍스트 추출 후 파일 삭제"""
    suffix = os.path.splitext(file.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        return extract_text_from_team_filepath(tmp_path)
    finally:
        os.remove(tmp_path)

def extract_text_from_team_filepath(file_path: str) -> str:
    """파일 경로 기반 텍스트 추출"""
    filename = os.path.basename(file_path).lower()

    if filename.endswith(".pdf"):
        text_chunks = []
        with fitz.open(file_path) as doc:
            for page in doc:
                try:
                    text = page.get_text()
                    text = text.encode("utf-8", errors="replace").decode("utf-8")
                    text_chunks.append(text)
                except Exception as e:
                    text_chunks.append(f"[페이지 오류: {e}]")
        return "\n".join(text_chunks)

    elif filename.endswith(".docx"):
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])

    elif filename.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    else:
        raise ValueError(f"지원하지 않는 파일 형식: {filename}")

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 50) -> list[str]:
    """텍스트를 청크 단위로 분할"""
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    return splitter.split_text(text)