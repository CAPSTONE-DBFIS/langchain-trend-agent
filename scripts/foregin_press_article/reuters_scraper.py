import requests

def main():
    # 스크래핑할 URL 고정
    url = "https://www.reuters.com/technology/"

    # HTTP 요청 보내기
    response = requests.get(url)

    # 응답이 성공적으로 반환되었는지 확인
    if response.status_code == 200:
        print("응답 성공적으로 반환됨!")
    else:
        print(f"페이지를 불러오는 데 실패했습니다. 상태 코드: {response.status_code}")

if __name__ == "__main__":
    main()