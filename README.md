# 📰 뉴스 크롤링 및 분석 시스템
국내 및 해외 뉴스 기사를 크롤링하고, 데이터를 저장 및 분석하는 프로젝트입니다. 크롤링된 데이터는 Flask 서버를 통해 제공되며, Milvus 벡터 데이터베이스에 업로드하여 검색 기능을 지원합니다.

# 📌 프로젝트 개요
이 프로젝트는 다음과 같은 주요 기능을 수행합니다:

국내 뉴스 기사 크롤링: 국내 뉴스 사이트에서 기사 수집 및 파싱
해외 뉴스 기사 크롤링: Ars Technica, NYT, TechCrunch 등 해외 뉴스 사이트에서 기사 수집 및 번역
기사 분류 및 키워드 분석: NLP를 활용한 키워드 추출 및 분석
Flask 서버 제공: 크롤링된 데이터를 REST API로 제공
Milvus 벡터 데이터베이스 업로드: 크롤링된 데이터의 검색 및 저장

# 🛠️ 프로젝트 디렉터리 구조
```
crawling/
│
├── configs/            # 설정 파일 디렉터리
│   └── config.yaml     # 프로젝트 설정 파일 (Git Ignore 설정)
│
├── data/               # 크롤링된 데이터 저장 디렉터리
│   ├── raw/            # 원본 데이터
│   ├── processed/      # 전처리된 데이터
│   └── output/         # 최종 결과물
│
├── logs/               # 로그 파일 저장 디렉터리
│   └── project.log     # 로그 파일
│
├── notebooks/          # Jupyter Notebook 파일 저장 디렉터리 (데이터 탐색, 테스트 등)
│   └── analysis.ipynb  # 데이터 분석용 노트북
│
├── scripts/            # 크롤링 및 데이터 처리 스크립트 디렉터리
│   │
│   ├── domestic_article/  # 국내 기사 관련 모듈
│   │   ├── classification.py  # 기사 분류 (키워드 빈도수 분석)
│   │   ├── main.py           # 국내 기사 크롤링 메인 실행 파일
│   │   ├── parser.py         # 국내 기사 HTML 파싱
│   │   ├── rag.py            # RAG(Reinforcement Augmented Generation) 관련 코드
│   │   └── scraper.py        # 국내 기사 스크래핑 관련 코드
│   │
│   ├── foreign_press_article/ # 해외 기사 관련 모듈
│   │   ├── ars_technica_scraper.py   # Ars Technica 기사 크롤러
│   │   ├── data_upload_milvus.py     # Milvus 벡터 DB 업로드 관련 코드
│   │   ├── itworld_scraper.py        # ITWorld 기사 크롤러
│   │   ├── main.py                   # 해외 기사 크롤링 메인 실행 파일
│   │   ├── nyt_scraper.py             # 뉴욕타임즈(NYT) 기사 크롤러
│   │   ├── techcrunch_scraper.py      # TechCrunch 기사 크롤러
│   │   ├── translator.py              # 기사 번역 모듈
│   │   └── zdnet_scraper.py           # ZDNet 기사 크롤러
│   │
│   ├── flask_server/  # Flask 서버 관련 코드
│   │   ├── templates/          # HTML 템플릿 디렉터리
│   │   ├── flask_server.py      # Flask 서버 메인 실행 파일
│   │   ├── test_db.py           # 데이터베이스 테스트 코드
│   │   └── test_flask.py        # Flask 서버 테스트 코드
│
├── tests/              # 테스트 코드 디렉터리
│   ├── test_scraper.py # 크롤링 테스트
│   ├── test_parser.py  # 파싱 테스트
│   └── test_db.py      # 데이터베이스 관련 테스트
│
├── requirements.txt    # 프로젝트 의존성 패키지 리스트
├── README.md           # 프로젝트 설명 파일
└── .env                # 환경 변수 파일 (API 키, 데이터베이스 비밀번호 등)
```
# 🚀 설치 및 실행 방법
## 1️⃣ 환경 설정
필요한 패키지를 설치하려면 다음 명령어를 실행하세요.

```
pip install -r requirements.txt
```

또는 가상 환경을 사용하는 경우:

```
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```
## 2️⃣ 환경 변수 설정
.env 파일을 생성하고, API 키 및 데이터베이스 정보를 설정하세요.
```
#Jenkins
JENKINS_ID=your_ID
JENKINS_PASSWORD=your_PASSSWORD
JENKINS_NAME=your_NAME
JENKINS_EMAIL=your_EMAIL
JENKINS_URL=your_URL

#Flask DB Config
DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=your_database_host
DB_PORT=your_database_port

#DeepL
DeepL_API_KEY=your_API_KEY
#MILVUS
MILVUS_HOST=your_HOST
MILVUS_PORT=your_PORT
```
## 3️⃣ 크롤링 실행
국내 뉴스 크롤링
```
python scripts/domestic_article/main.py
```
해외 뉴스 크롤링
```
python scripts/foreign_press_article/main.py
```
## 4️⃣ Flask 서버 실행
```
python scripts/flask_server/flask_server.py
```
이제 API를 통해 데이터를 조회할 수 있습니다.

# 📡 API 사용법 문서
이 문서는 Flask 서버에서 제공하는 REST API 엔드포인트와 사용법을 설명합니다.

## 🌍 기본 서버 정보
Base URL: http://localhost:8080
응답 형식: JSON (application/json)
### 🏠 1. 서버 상태 확인
GET /
서버가 정상적으로 작동하는지 확인하는 엔드포인트입니다.

🔹 요청 예시
``` html
GET http://localhost:8080/
```
🔹 응답 예시

``` json
{
  "message": "Server is running!"
}
```
### 📰 기사 데이터 관리
🔹 2. 국내 기사 데이터 조회
```
GET /api/articles
```
저장된 모든 국내 기사 데이터를 JSON 형태로 반환합니다.

🔹 요청 예시

```
GET http://localhost:8080/api/articles
```
🔹 응답 예시

``` json
[
  {
    "id": 1,
    "category": "정치",
    "media_company": "조선일보",
    "title": "대통령, 경제 회복 대책 발표",
    "date": "2024-03-15",
    "image": "https://example.com/image.jpg",
    "url": "https://example.com/article1",
    "summary": "경제 회복 대책이 발표되었습니다."
  }
]
```
🔹 3. 국내 기사 데이터 HTML 렌더링
```
GET /articles
```
저장된 기사 데이터를 HTML 페이지로 렌더링합니다.

🔹 요청 예시

```
GET http://localhost:8080/articles
```
🔹 응답

HTML 테이블 형식으로 렌더링된 기사 데이터

🔹 4. 국내 기사 데이터 업로드
```
POST /upload
```
새로운 국내 기사를 추가합니다.

🔹 요청 헤더

``` pgsql
Content-Type: application/json
```
🔹 요청 예시

``` http
POST http://localhost:8080/upload
``` 
``` json
{
  "category": "정치",
  "media_company": "조선일보",
  "title": "대통령, 경제 회복 대책 발표",
  "date": "2024-03-15",
  "image": "https://example.com/image.jpg",
  "url": "https://example.com/article1",
  "summary": "경제 회복 대책이 발표되었습니다."
}
```
🔹 응답 예시

``` json
{
  "message": "Article added successfully",
  "id": 1
}
```
🔹 5. 특정 국내 기사 삭제
```
DELETE /delete_article/{article_id}
```
특정 ID의 기사를 삭제합니다.

🔹 요청 예시

``` http
DELETE http://localhost:8080/delete_article/1
```
🔹 응답 예시

``` json
{
  "message": "Article deleted successfully",
  "id": 1
}
```
### 🌍 해외 기사 데이터 관리
🔹 6. 해외 기사 데이터 조회 (HTML)
```
GET /foreign_articles
```
저장된 해외 뉴스 기사 데이터를 HTML 테이블로 렌더링합니다.

🔹 요청 예시

``` http
GET http://localhost:8080/foreign_articles
```
🔹 응답

HTML 테이블 형식으로 렌더링된 해외 기사 데이터

🔹 7. 해외 기사 데이터 업로드
```
POST /api/foreign_articles/upload
```
새로운 해외 기사를 추가합니다.

🔹 요청 헤더

``` pgsql
Content-Type: application/json
```
🔹 요청 예시

``` http
POST http://localhost:8080/api/foreign_articles/upload
```
``` json
{
  "url": "https://example.com/foreign-news",
  "title": "Global Economic Growth Report",
  "date": "2024-03-15",
  "description": "The global economy is expected to grow by 3%."
}
```
🔹 응답 예시

``` json
{
  "message": "Article added successfully",
  "id": 5
}
```
