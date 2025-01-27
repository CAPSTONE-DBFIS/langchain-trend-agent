import requests

"""현재는 간단한 응답 확인 코드만 작성한 상태. 아래에서 사용된 url을 사용하여 스크래핑할 것.
참고 사항은 백엔드 1월 27일자 회의에 기록함."""

def main():
    # 스크래핑할 URL 고정
    url = "https://www.itworld.co.kr/opinion/"

    # HTTP 요청 보내기
    response = requests.get(url)

    # 응답이 성공적으로 반환되었는지 확인
    if response.status_code == 200:
        print("응답 성공적으로 반환됨!")
    else:
        print(f"페이지를 불러오는 데 실패했습니다. 상태 코드: {response.status_code}")

if __name__ == "__main__":
    main()