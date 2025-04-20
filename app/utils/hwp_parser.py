import subprocess
import tempfile
import os

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