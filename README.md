# TRENDB - LangChain Trend Agent
<img width="654" alt="image" src="https://github.com/user-attachments/assets/9b518f95-a34f-491a-8ff5-2370fa3da076">

## 개요

TRENDB는 다양한 AI 도구와 연동하여 뉴스, 커뮤니티, 논문 등 최신 IT 트렌드 정보를 분석하여 검증된 출처를 기반으로 신뢰성 있는 답변을 제공하는 AI Agent 챗봇 시스템입니다.

---

## 프로젝트 구조

```
langchain-trend-agent
├── .github
├── app
│   ├── services
│   │   ├── agent_service.py
│   │   ├── team_file_ops_service.py
│   │   └── team_file_rag_service.py
│   ├── tools
│   │   ├── tools.py
│   │   └── tools_schema.py
│   ├── utils
│   │   ├── db_util.py
│   │   ├── es_util.py
│   │   ├── file_util.py
│   │   ├── milvus_util.py
│   │   ├── redis_util.py
│   │   ├── s3_util.py
│   │   └── team_file_util.py
│   └── main.py
```

---

## 주요 기능

### 1. AI 에이전트 챗봇

* 다양한 LLM 모델(GPT-4o-mini, Claude Sonnet, Grok-3 등)과 연계한 도구 호출 기반 실시간 트렌드 분석 기능 제공
* 사용자의 쿼리에 따라 AI 에이전트가 적절한 도구를 자동 호출하여 응답 제공
* 업로드된 파일 내용 기반 질의응답 가능
* 페르소나 - 사용자가 설정한 말투, 어휘, 성격 등을 반영한 맞춤형 응답 제공

### 2. 팀 파일 관리 및 RAG 서비스

* 팀 파일 업로드 및 Milvus 기반 벡터 임베딩 관리
* 팀 문서 기반 질의응답(RAG)

---

## 응답 처리 플로우
![TRENDB flow chart](images/flow_chart.png)
1. 사용자의 질의 입력
2. 채팅 기록 로딩, 업로드 파일 텍스트 추출 및 메모리 삽입, 사용자 페르소나 불러오기 (채팅방의 첫 질문일 경우, 채팅방 이름 변경)
3. 에이전트 초기화(LLM + 프롬프트 + 도구 + 메모리)
4. 사용자 질의를 분석하여 가장 적절한 도구를 단일/병렬 호출 -> 도구 호출 로그 SSE 스트리밍
5. 도구 결과 반환 -> 도구 결과 로그 SSE 스트리밍
6. 도구 출력 기반 응답 생성 -> 응답 토큰 실시간 SSE 스트리밍
7. 채팅 로그 및 응답 저장

---

## 구현된 도구
| 도구명                   | 설명                                                                                                                     | 주요 옵션                                                                                                                           |
|------------------------|------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| 트렌드 키워드 분석 도구       | DB에 저장된 국내 IT 뉴스 키워드 데이터를 조회하여, 지정 기간(일간/주간/월간) 상위 키워드 빈도와 감정 분포(긍정/중립/부정)를 집계한 뒤 스택형 바 차트와 해당 키워드별 기사 목록을 반환합니다. | `period` (string), `date` (string)                                                                                              |
| 국내 IT 뉴스 검색 도구       | Elasticsearch에 저장된 국내 IT 뉴스 인덱스에서 키워드를 기반으로 지정 날짜 범위 내 최신 순으로 최대 개수의 기사를 검색해 제목, 요약, 날짜, URL, 매체 정보를 반환합니다.              | `keyword` (string), `start_date` (string), `end_date` (string), `max_results` (int)                                                 |
| 해외 IT 뉴스 검색 도구       | GNews API를 이용해 영어 키워드 기반 해외 IT 뉴스 기사를 검색하고 제목, 본문 요약, 날짜, URL, 매체 정보를 반환합니다.                                                   | `en_keyword` (string), `lang` (string), `country` (string), `max_results` (int)                                                     |
| 트렌드 리포트 생성 도구      | 국내·해외 IT 뉴스 상위 키워드 빈도 및 감정 분포 차트를 생성하고 기사 요약과 함께 서술형 보고서를 DOCX 파일로 만들어 다운로드 가능한 S3 URL을 반환합니다.                     | `start_date` (string), `end_date` (string)                                                                                          |
| 웹 검색 도구              | Tavily API를 사용해 키워드 기반 실시간 웹페이지 검색 결과(제목, 내용, URL 등)를 JSON 형태로 반환합니다.                                                                   | `keyword` (string), `max_results` (int), `include_images` (bool)                                                                    |
| 경쟁사 분석 도구            | 미리 정의된 경쟁사 목록을 기준으로 Elasticsearch에서 언급량과 감정 분포를 집계하여 스택형 바 차트를 생성하고 각 경쟁사별 대표 기사 목록을 반환합니다.                       | `start_date` (string), `end_date` (string)                                                                                          |
| 구글 트렌드 도구           | PyTrends를 사용해 지정 키워드의 Google 트렌드 관심도 시계열 데이터를 조회하고 선 그래프를 생성하여 S3 URL과 함께 관심도 데이터를 반환합니다.                               | `query` (string), `start_date` (string), `end_date` (string)                                                                         |
| 커뮤니티 검색 도구          | Naver/Daum 블로그, Reddit, X(Twitter)에서 병렬로 게시물을 검색하여 플랫폼별 균등 분배 후 최신 순으로 결과를 반환하며 오류 발생 시 에러 정보를 함께 제공합니다.               | `korean_keyword` (string), `english_keyword` (string), `platform` (string), `max_results` (int)                                       |
| 유튜브 검색 도구           | YouTube Data API를 통해 키워드 기반으로 동영상을 검색하고 videoId, 제목, 설명, 채널, 게시일, 썸네일 URL, 동영상 URL 정보를 반환합니다.                                      | `query` (string), `max_results` (int), `order` (string)                                                                              |
| 웹페이지/문서 추출 도구       | HTML 또는 PDF URL에서 본문 텍스트를 추출하여 반환하며 HTML은 본문 최대 5000자, PDF는 전체 내용을 추출합니다.                                                           | `input_url` (string)                                                                                                                  |
| 위키피디아 검색 도구         | 한국어 위키피디아를 우선 검색해 요약을 제공하고 실패 시 영어 위키피디아를 대체하여 최대 1500자 요약 결과를 반환합니다.                                                   | `query` (string)                                                                                                                       |
| 나무위키 검색 도구          | 나무위키 문서를 크롤링하여 불필요한 요소를 제거한 뒤 최대 30개의 유효 문단을 반환합니다.                                                                              | `keyword` (string)                                                                                                                     |
| 주식 조회 도구            | FinanceDataReader 또는 yfinance를 통해 글로벌 또는 한국 주식의 OHLCV 데이터를 조회하고 종가·거래량 차트를 생성하여 S3 URL과 함께 반환합니다.                                  | `symbol` (string), `start_date` (string), `end_date` (string)                                                                          |
| 이미지 생성 도구           | ChatOpenAI(GPT-4o-mini)를 사용해 한국어 프롬프트를 영어로 변환한 뒤 DALL·E 3로 고품질 이미지를 생성하여 URL을 반환합니다.                                                | `prompt` (string)                                                                                                                      |
| 논문 검색 도구            | OpenAlex API를 이용해 학술 논문을 검색하고 논문 제목, 초록, 출판일, URL, 저자 정보를 반환합니다.                                                                            | `query` (string), `max_results` (int), `start_date` (string), `end_date` (string), `sort_by` (string)                                  |
---

## 기술 스택 및 브랜치 전략
### 기술 스택

- **인프라**: FastAPI, Spring Boot, Redis, Milvus, Elasticsearch, PostgreSQL (RDS), AWS EC2, S3, GoogleCloud, Docker  
  **운영/시각화**: Kibana, Attu, LangSmith

- **LLM 모델**: OpenAI GPT-4o-mini, GPT-4.1, Anthropic Claude Sonnet 4, XAI Grok-3

- **도구 및 라이브러리**: LangChain, FinanceDataReader, yfinance, TavilySearch, BeautifulSoup, Pydantic, Plotly, Matplotlib 등

- **DevOps & 배포 자동화**: GitHub Actions, Jenkins

- **협업 도구**: Notion(https://www.notion.so/11336a22fce780588e9ed8863065d14b?v=11336a22fce78162a28d000cca19cb42&pvs=4), Google Meet, Discord
### 브랜치 전략
* **main: 배포용 브랜치(Github Actions 연동)**
* **develop: 개발 통합 브랜치**
* **feature/*: 기능 개발 후 통합 시 삭제**

## 서버 아키텍처 및 사양

### 서버 아키텍처
![system_architecture.png](images/system_architecture.png)

| 서버 종류             | 주요 역할                     | 구성 및 설명                                                                        |
|-------------------|---------------------------|--------------------------------------------------------------------------------|
| 메인 Application 서버 | 프론트엔드 및 사용자 요청 백엔드 처리     | React + FastAPI + Spring 연동                                                    |
| DB 서버             | 데이터 저장 및 검색 인프라 구성        | Elasticsearch + Milvus + Redis                                    |
| 크롤링 서버            | 뉴스 크롤링 및 데이터 분석 파이프라인 자동화 | Jenkins + Python 크롤러, 메인, 연관 키워드 추출 및 klue/bert-base 감정 분류 모델 구동 파이프라인 주기적 스케줄링 |

### 서버 권장 사양

| 서버 종류   | vCPU | 메모리 | 디스크  | 비고                          |
|------------|------|-----|------|-----------------------------|
| 메인 서버   | 4    | 8GB | 50GB | 실시간 응답 처리, FastAPI+Spring   |
| DB 서버    | 4    | 8GB | 50GB | Elasticsearch, Milvus 등 운영  |
| Jenkins 서버 | 2    | 8GB | 50GB | 크롤링, 키워드 추출, 감정 분석, 자동화 작업용 |
---

## API 엔드포인트

| 경로                                | 설명                 | 메소드    |
| --------------------------------- | ------------------ | ------ |
| `/agent/query`                    | AI 에이전트 질의응답       | POST   |
| `/team-files`                     | 팀 파일 업로드 및 임베딩 저장  | POST   |
| `/team-files/{team_id}/{file_id}` | 팀 파일 삭제 및 임베딩 삭제   | DELETE |
| `/team-file/query`                | 팀 파일 기반 질의응답 (RAG) | POST   |

---

## 실행 방법

### 설치

```bash
git clone https://github.com/CAPSTONE-DBFIS/langchain-trend-agent.git
cd langchain-trend-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 서버 실행

```bash
uvicorn app.main:app --reload
```

---

## 로깅 및 모니터링

* FastAPI 로그 확인
* Redis 캐싱 모니터링
* Milvus 관리 도구 Attu 사용
* ElasticSearch 관리 도구 Kibana 사용
---

## 배포

* GitHub Actions 기반 CI/CD

---
