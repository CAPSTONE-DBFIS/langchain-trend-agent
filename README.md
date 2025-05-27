# TRENDB - LangChain Trend Agent
<img width="654" alt="image" src="https://github.com/user-attachments/assets/9b518f95-a34f-491a-8ff5-2370fa3da076">

## 개요

TRENDB는 다양한 AI 도구와 연동하여 뉴스, 커뮤니티, 논문 등 최신 IT 트렌드 정보를 분석하여 검증된 출처를 기반으로 신뢰성 있는 답변을 제공하는 AI Agent 챗봇 시스템입니다.

---

## 프로젝트 구조

```
crawling
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

1. 사용자의 질의 입력
2. 채팅 기록 로딩, 업로드 파일 텍스트 추출 및 메모리 삽입, 사용자 페르소나 불러오기 (채팅방의 첫 질문일 경우, 채팅방 이름 변경)
3. 에이전트 초기화(LLM + 프롬프트 + 도구 + 메모리)
4. 사용자 질의를 분석하여 가장 적절한 도구를 단일/병렬 호출 -> 도구 호출 로그 SSE 스트리밍
5. 도구 결과 반환 -> 도구 결과 로그 SSE 스트리밍
6. 도구 출력 기반 응답 생성 -> 응답 토큰 실시간 SSE 스트리밍
7. 채팅 로그 및 응답 저장

---

## 구현된 도구

* **domestic\_it\_news\_search\_tool**: 크롤링 IT 뉴스 기사 기반 Elasticsearch를 이용한 국내 IT 뉴스 검색 및 분석
* **foreign\_news\_search\_tool**: GNews API 기반 해외 뉴스 검색 및 분석
* **it\_news\_trend\_keyword\_tool**: 키워드 빈도 및 감정 분석 데이터를 통한 국내 뉴스 트렌드 분석
* **global_it_news_trend_report_tool**: 기간내 키워드 빈도, 크롤링 IT 뉴스 기반 자동화된 트렌드 보고서 생성
* **google\_trends\_tool**: Google 트렌드 데이터 시계열 분석
* **community\_search\_tool**: Naver, Daum 블로그 및 Reddit, X(트위터) 게시물 검색
* **youtube\_video\_tool**: YouTube API를 이용한 관련 비디오 검색
* **request\_url\_tool**: 웹페이지 및 PDF에서 텍스트 추출
* **wikipedia\_tool**: Wikipedia에서 개념 및 정의 검색
* **namuwiki\_tool**: 나무위키에서 관련 정보 검색
* **stock\_history\_tool**: 주식 데이터 및 차트 분석
* **dalle3\_image\_generation\_tool**: DALL·E 3를 이용한 이미지 생성
* **paper\_search\_tool**: OpenAlex API 기반 최신 논문 검색 및 분석

---

## 기술 스택 및 브랜치 전략
### 기술 스택

- **인프라**: FastAPI, Spring Boot, Redis, Milvus, Elasticsearch, PostgreSQL (RDS), AWS EC2, S3, GoogleCloud, Docker  
  **운영/시각화**: Kibana, Attu, LangSmith

- **LLM 모델**: OpenAI GPT-4o-mini, GPT-4.1, Anthropic Claude Sonnet 4, XAI Grok-3

- **도구 및 라이브러리**: LangChain, FinanceDataReader, yfinance, TavilySearch, BeautifulSoup, Pydantic, Plotly, Matplotlib 등

- **DevOps & 배포 자동화**: GitHub Actions, Jenkins

- **협업 도구**: Notion(https://www.notion.so/1f036a22fce780139732c23234d6fbfa?pvs=4), Google Meet, Discord
### 브랜치 전략
* **main: 배포용 브랜치(Github Actions 연동)**
* **develop: 개발 통합 브랜치**
* **feature/*: 기능 개발 후 통합 시 삭제**

## 서버 아키텍처 및 사양

### 서버 아키텍처
| 서버 종류      | 주요 역할                  | 구성 및 설명                                                               |
|------------|------------------------|-----------------------------------------------------------------------|
| 메인 서버      | 프론트엔드 및 사용자 요청 백엔드 처리  | React + FastAPI + Spring 연동                                   |
| DB 서버      | 데이터 저장 및 검색 인프라 구성     | Elasticsearch + Milvus + Redis + PostgreSQL                           |
| Jenkins 서버 | 뉴스 크롤링 및 데이터 파이프라인 자동화 | Jenkins + Python 크롤러, 메인, 연관 키워드 추출 및 BERT 감정 분류 모델 구동 파이프라인 주기적 스케줄링 |

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
* Redis 캐싱 효율 모니터링
* Milvus 관리 도구 Attu 사용

---

## 배포

* GitHub Actions 기반 CI/CD

---
