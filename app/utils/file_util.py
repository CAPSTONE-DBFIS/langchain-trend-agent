from fastapi import UploadFile
import fitz
import docx
import olefile
from io import BytesIO
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import subprocess
import tempfile
import os

BASE_UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/uploads"))

async def save_upload_file_to_disk(file: UploadFile, uploader_id: str):
    uploader_path = os.path.join(BASE_UPLOAD_DIR, uploader_id)
    os.makedirs(uploader_path, exist_ok=True)

    file_path = os.path.join(uploader_path, file.filename)
    contents = await file.read()

    with open(file_path, "wb") as f:
        f.write(contents)

    return file_path

def extract_text_by_filename(uploader_id: str, filename: str) -> str:
    """
    업로드된 파일에서 원본 텍스트를 추출
    """
    file_path = os.path.join(BASE_UPLOAD_DIR, uploader_id, filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"파일이 존재하지 않음: {file_path}")

    with open(file_path, "rb") as f:
        contents = f.read()

    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf"):
        return extract_pdf(contents)
    elif filename_lower.endswith(".docx"):
        return extract_docx(contents)
    elif filename_lower.endswith(".hwp"):
        return extract_hwp(contents)
    elif filename_lower.endswith(".txt"):
        return extract_txt(contents)
    elif filename_lower.endswith((".png", ".jpg", ".jpeg")):
        return extract_image(contents)
    else:
        raise Exception("지원하지 않는 파일 형식입니다.")


def extract_pdf(contents: bytes) -> str:
    """PDF 파일의 내용을 텍스트로 추출합니다."""
    text = ""
    with fitz.open(stream=contents, filetype="pdf") as doc:
        for page in doc:
            try:
                page_text = page.get_text("text")
                text += page_text
            except Exception as e:
                print(f"[ERROR] 페이지 텍스트 추출 실패: {e}")
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore").strip()

def extract_docx(contents: bytes) -> str:
    """DOCX 파일에서 텍스트 추출"""
    doc = docx.Document(BytesIO(contents))
    return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])

def extract_hwp(contents: bytes) -> str:
    """HWP 텍스트 추출 (OLE 기반)"""
    buffer = BytesIO(contents)
    if not olefile.isOleFile(buffer):
        raise ValueError("올바르지 않은 HWP 파일입니다.")
    buffer.seek(0)
    try:
        raw_text = extract_text_from_hwp_binary(buffer.read())
        return raw_text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore").strip()
    except Exception as e:
        print(f"[ERROR] HWP 텍스트 추출 오류: {e}")
        return ""
def extract_text_from_hwp_binary(binary: bytes) -> str:
    """
    pyhwp에서 제공하는 hwp5txt CLI를 사용해 HWP 파일에서 텍스트 추출
    ! 배포 시 pyhwp 설치 필요, hwp5txt CLI가 PATH에 있어야 함 !
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".hwp") as tmp:
        tmp.write(binary)
        tmp.flush()
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["hwp5txt", tmp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"HWP 추출 실패: {result.stderr.strip()}")
        return result.stdout
    finally:
        os.unlink(tmp_path) # 파일 삭제

def extract_txt(contents: bytes) -> str:
    """TXT 파일에서 텍스트 추출"""
    try:
        text = contents.decode("utf-8", errors="ignore").strip()
        return text
    except Exception as e:
        print(f"[ERROR] TXT 텍스트 추출 오류: {e}")
        return ""


def extract_image(contents: bytes) -> str:
    """이미지 파일에서 텍스트를 OCR로 추출"""
    try:
        image = Image.open(BytesIO(contents))
        if image.mode != "RGB":
            image = image.convert("RGB")

        # 전처리: 기울기 보정, 이진화
        image = ImageOps.autocontrast(image)
        image = image.convert("L")
        image = image.point(lambda x: 0 if x < 128 else 255, mode="1")

        # 해상도 개선
        width, height = image.size
        if width < 1000 or height < 1000:
            new_width = max(1000, width * 2)
            new_height = max(1000, height * 2)
            image = image.resize((new_width, new_height), Image.LANCZOS)

        # 텍스트 추출
        text = pytesseract.image_to_string(image, lang='kor+eng', config='--psm 3 --oem 1')
        return text.strip()
    except Exception as e:
        print(f"[ERROR] 이미지 텍스트 추출 오류: {e}")
        return ""

