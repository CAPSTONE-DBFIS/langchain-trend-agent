<p align="center">
  <a href="https://github.com/CAPSTONE-DBFIS/langchain-trend-agent">
    <img src=".github/assets/trendb_logo.png" alt="TRENDB Logo" width="150">
  </a>
</p>
<h1 align="center">TRENDB: IT 트렌드 분석 AI 에이전트</h1>
<p align="center">다양한 도구를 활용하여 IT 업계 트렌드에 대한 <b>인사이트</b>를 제공하는 지능형 에이전트</p>
<p align="center"><strong>프로젝트 기간: 2024.07.10 ~ 2025.06.04</strong></p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10-3776AB.svg?style=flat-square&logo=python" alt="Python"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688.svg?style=flat-square&logo=fastapi" alt="FastAPI"></a>
  <a href="https://www.langchain.com/"><img src="https://img.shields.io/badge/LangChain-0.3-8A2BE2.svg?style=flat-square" alt="LangChain"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-blue.svg?style=flat-square&logo=postgresql" alt="PostgreSQL"></a>
  <a href="https://milvus.io/"><img src="https://img.shields.io/badge/Milvus-4FC8E0.svg?style=flat-square&logo=milvus" alt="Milvus"></a>
  <a href="https://www.elastic.co/kr/elasticsearch/"><img src="https://img.shields.io/badge/Elasticsearch-005571.svg?style=flat-square&logo=elasticsearch" alt="Elasticsearch"></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-DC382D.svg?style=flat-square&logo=redis" alt="Redis"></a>
  <a href="https://aws.amazon.com/"><img src="https://img.shields.io/badge/AWS-232F3E.svg?style=flat-square&logo=amazon-aws" alt="AWS"></a>
  <a href="https://aws.amazon.com/s3/"><img src="https://img.shields.io/badge/Amazon_S3-569A31.svg?style=flat-square&logo=amazon-s3" alt="Amazon S3"></a>
</p>

## 1. 🚀 프로젝트 소개

### 개발 목적
급변하는 기술 환경 속에서 실시간으로 쏟아지는 방대한 정보들을 한눈에 파악하고, 비즈니스 변화에 신속하게 대응하는 것은 모든 기업의 중요한 과제입니다. **TRENDB**는 이러한 필요성에 따라 임직원들이 최신 IT 트렌드를 놓치지 않고, 데이터에 기반하여 올바른 방향성을 설정할 수 있도록 지원하기 위해 개발되었습니다.

**TRENDB**는 기존 거대 언어 모델(LLM)의 가장 큰 한계점인 **환각(Hallucination) 현상을 최소화**하고, **신뢰할 수 있는 최신 정보**를 제공하는 것을 핵심 목표로 삼는 지능형 에이전트입니다.

이를 위해, 단순히 LLM에 의존하는 대신 **자체적으로 구축한 데이터 파이프라인**을 통해 매일 수집되는 검증된 데이터를 기반으로 답변을 생성합니다. 모든 정보는 명확한 출처와 함께 제공되어, 사용자는 다음과 같은 가치를 얻을 수 있습니다.

- **검증 가능한 정보 습득**: 신뢰도 높은 최신 데이터를 기반으로 사실에 입각한 답변을 얻을 수 있습니다.
- **신속한 동향 파악**: 자동화된 분석 및 시각화 자료를 통해 복잡한 IT 트렌드를 직관적으로 파악할 수 있습니다.
- **데이터 기반 의사결정 지원**: 정보 탐색에 드는 시간을 줄이고, 검증된 데이터를 바탕으로 더 빠르고 정확한 의사결정을 내릴 수 있도록 지원하며, 나아가 비즈니스 방향성을 제시합니다.

---

## 2. ✨ 핵심 기능 및 구현

TRENDB의 핵심은 **LangChain 기반의 자율적 에이전트**가 15개 이상의 도구(Tool)를 활용하여 사용자의 질문을 해결하는 것에 있습니다. 에이전트는 복잡한 요구사항을 스스로 분석하여 최적의 실행 계획을 수립하고, 여러 도구를 유기적으로 조합해 다각적인 분석을 수행합니다. 이 과정에서 생성된 시각화 자료는 S3에 업로드 되고, 이미지 형태로 함께 제공되어 사용자의 직관적인 이해를 돕습니다.

### 2.1. 시장 및 트렌드 분석

-   **트렌드 키워드 분석**: 국내 뉴스 데이터를 기반으로 기간별(일/주/월) 트렌드 키워드를 추출하고, 언급량과 감성 분포를 차트로 시각화하여 기사 본문 요약과 함께 제공합니다.
-   **경쟁사 동향 분석**: 지정된 경쟁사들의 뉴스 언급량 및 감성 추이를 분석하고, 관련 대표 기사를 함께 제시하여 심도 있는 비교 분석을 지원합니다.
-   **구글 트렌드 분석**: `Pytrends`를 활용하여 특정 키워드의 관심도 변화를 시계열 그래프로 시각화하여, 대중의 관심도 추이를 직관적으로 파악할 수 있습니다.
-   **국내외 주식 분석**: `FinanceDataReader`와 `yfinance`를 통해 국내외 주식의 OHLCV 데이터를 조회하고, 종가 및 거래량 차트를 생성하여 시장 반응을 분석합니다.

<p align="center">
  <img src=".github/assets/feature_keyword_analysis_period.png" width="350" height="500" alt="기간별 트렌드 키워드 분석">
  <img src=".github/assets/feature_keyword_analysis_keyword.png" width="350" height="500" alt="특정 키워드 트렌드 분석">
  <br>
  <em>기간별 상위 키워드 트렌드 분석(좌) 및 특정 키워드 심층 분석(우)</em>
</p>
<p align="center">
  <img src=".github/assets/feature_competitor_analysis.png" width="700" alt="경쟁사 동향 분석">
  <br>
  <em>경쟁사별 뉴스 언급량 및 감성 분포 분석</em>
</p>
<p align="center">
  <img src=".github/assets/feature_stock_analysis.png" width="700" alt="국내외 주식 분석">
  <br>
  <em>주가 및 거래량 변동 추이 시각화</em>
</p>

### 2.2. 다중 소스 정보 검색 및 분석

-   **국내외 뉴스 검색**: 자체 구축한 Elasticsearch 뉴스 데이터베이스에서 국내외 기사를 실시간으로 검색하고, 핵심 내용을 요약하여 제공합니다.
-   **웹 & 커뮤니티 검색**: Tavily 웹 검색, 네이버/다음 블로그, Reddit, X(Twitter) 등 다양한 채널을 병렬로 탐색하여 최신 정보와 여론을 종합적으로 수집합니다.
-   **전문 정보 검색**: Wikipedia, 나무위키, OpenAlex(학술 논문), YouTube 등 특정 도메인에 특화된 검색을 수행하여 정보의 깊이와 신뢰도를 높입니다.
-   **웹/문서 내용 추출**: 사용자가 제공한 URL(웹페이지, PDF)의 텍스트를 직접 추출하고 분석하여, 별도의 검색 없이 원하는 정보에 바로 접근할 수 있습니다.

<p align="center">
  <img src=".github/assets/feature_community_search.png" width="700" alt="웹 & 커뮤니티 검색">
  <br>
  <em>다중 커뮤니티 동시 검색 결과</em>
</p>
<p align="center">
  <img src=".github/assets/feature_paper_search.png" width="350" alt="논문 검색">
  <img src=".github/assets/feature_youtube_search.png" width="350" alt="유튜브 검색">
  <br>
  <em>논문 검색(좌) 및 유튜브 영상 검색(우)</em>
</p>
<p align="center">
  <img src=".github/assets/feature_url_extraction.png" width="700" alt="웹/문서 내용 추출">
  <br>
  <em>URL 기반 웹페이지 내용 추출 및 요약</em>
</p>

### 2.3. 콘텐츠 생성 및 지식 확장

-   **자동 리포트 생성**: 여러 분석 도구의 결과를 종합하고, LLM이 서술형 분석까지 더한 전문적인 트렌드 리포트(DOCX)를 자동으로 생성합니다.
-   **AI 이미지 생성**: DALL-E 3를 활용하여 사용자의 아이디어를 즉시 시각적인 이미지로 구체화합니다.
-   **팀 문서 기반 RAG (Retrieval-Augmented Generation)**: 팀 전용 클라우드에 문서(PDF, DOCX, TXT)를 업로드하면, 시스템이 자동으로 텍스트를 추출하고 의미 단위로 분할(Chunking)하여 벡터 임베딩으로 변환한 뒤 **Milvus**에 저장합니다. 이후 사용자가 팀 문서에 대해 질문하면, 질문과 코사인 유사도가 가장 높은 문서 내용을 찾아내 답변의 근거로 활용하여 정확하고 신뢰도 높은 답변을 생성합니다.
-   **문서 파일 첨부**: 대화 시 문서 파일(PDF, DOCX, HWP, TXT)을 첨부하면, 해당 파일에서 텍스트를 추출하여 일시적으로 대화의 문맥(Memory)에 주입됩니다. 이를 통해 AI 에이전트는 현재 대화에서만 첨부된 파일 내용을 기반으로 답변을 생성할 수 있습니다.


<p align="center">
  <img src=".github/assets/feature_report_generation.png" width="700" alt="자동 리포트 생성">
  <br>
  <em>자동 생성된 트렌드 리포트(DOCX) 다운로드</em>
</p>
<p align="center">
  <img src=".github/assets/feature_image_generation.png" width="700" alt="AI 이미지 생성">
  <br>
  <em>DALL-E 3를 활용한 이미지 생성</em>
</p>
<p align="center">
  <img src=".github/assets/feature_file_upload.png" width="700" alt="파일 첨부를 통한 대화 문맥 확장">
  <br>
  <em>업로드된 파일을 기반으로 한 질의응답</em>
</p>

### 2.4. 에이전트 시스템

-   **유연한 LLM 모델 선택**: GPT-4.1, Grok-3, Claude-Sonnet-3.7 등 검증된 여러 LLM을 사용자가 직접 선택하여, 성능, 목적에 따라 최적의 모델을 활용할 수 있습니다.
-   **사용자 맞춤형 페르소나**: 시스템에서 제공하는 프리셋을 사용하거나, 사용자가 직접 챗봇의 말투, 어조, 역할을 정의하는 커스텀 페르소나를 생성하여 개인화된 사용자 경험을 제공합니다.
-   **실시간 도구 실행 상태 제공**: 에이전트가 답변을 생성하기 위해 어떤 도구를 사용하고 있는지 그 실행 상태를 실시간으로 스트리밍하여, 사용자가 응답 생성 과정을 투명하게 확인할 수 있도록 했습니다.
-   **채팅방 제목 자동 생성**: 채팅방의 첫 번째 질문이 입력되면, LLM이 해당 질문의 핵심 내용을 자동으로 요약하여 채팅방의 제목으로 설정합니다. 이를 통해 사용자는 나중에 각 대화의 주제를 쉽게 식별할 수 있습니다.

<p align="center">
  <img src=".github/assets/feature_persona_selection.png" width="700" alt="사용자 맞춤형 페르소나">
  <br>
  <em>LLM 모델 선택 및 사용자 맞춤형 페르소나 설정</em>
</p>

### 2.5. 신뢰성 및 투명성

-   **실시간 출처 제공 및 검증**: 에이전트는 답변을 생성할 때 사용한 모든 정보의 출처(뉴스 기사, 웹페이지, 논문 등)를 답변과 함께 실시간으로 스트리밍합니다. 이를 통해 사용자는 AI가 제공한 정보의 근거를 명확히 확인하고 직접 검증할 수 있어, 답변의 신뢰성을 크게 높입니다.

<p align="center">
  <img src=".github/assets/feature_source.png" width="500" alt="실시간 출처 제공">
  <br>
  <em>실시간으로 제공되는 답변 및 출처 정보</em>
</p>

---

## 3. 🛠️ 기술 스택

| 구분 | 기술                                                                                                                                              | 상세 설명                                                            |
|---|-------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| **Backend** | `FastAPI`, `Python 3.10`                                                                                                                        | 비동기 방식으로 동작하는 API 서버 구축                                          |
| **LLM & AI** | `LangChain`, `OpenAI GPT-4.1`, `Claude Sonnet 3.7`, `Grok-3`                                                                                    | 에이전트, 체인, 메모리 등 핵심 로직 구현 및 최신 LLM 연동                             |
| **Database** | `PostgreSQL`, `Milvus`, `Elasticsearch`, `Redis`                                                                                                | 채팅/사용자 데이터 관리, 벡터 임베딩 저장, 뉴스 데이터 검색, 도구 결과 캐싱                    |
| **Infrastructure** | `AWS (EC2, S3)`, `Google Compute Engine`, `Docker`                                                                                              | 서버 배포(EC2, Compute Engine), 시각화 결과 저장(S3), 주요 컴포넌트 컨테이너화(Docker) |
| **Monitoring & Mgt.** | `LangSmith`, `Kibana`, `Attu`, `DBeaver`                                                                                                        | Elasticsearch 데이터 시각화, Milvus 벡터 DB 관리, PostgreSQL DB 관리         |
| **DevOps** | `GitHub Actions`, `Jenkins`                                                                                                                     | CI/CD 파이프라인, 데이터 수집 자동화                                          |
| **Core Libraries** | `Pandas`, `NumPy`, `Pydantic`, `Plotly`, `TavilySearch`, `BeautifulSoup`, `FinanceDataReader`, `yfinance`, `pytrends`, `python-docx`, `PyMuPDF` | 데이터 처리, 유효성 검증, 시각화, 웹/전문 정보 검색, 리포트 생성 등                        |

---

## 4. 🏛️ 관련 저장소 (Related Repositories)

TRENDB의 백엔드 시스템은 마이크로서비스 아키텍처(MSA)를 기반으로, 기능에 따라 분리된 3개의 애플리케이션 서버와 별도의 데이터베이스 서버로 구성됩니다. 각 애플리케이션 서버는 독립적인 저장소에서 관리됩니다.

-   **AI 에이전트 서버 (FastAPI)**: (현재 저장소) LangChain 기반의 AI 에이전트 및 15개 이상의 도구를 통해 사용자의 질문을 이해하고 답변을 생성하는 핵심 AI 서버입니다.
-   **메인 API 서버 (Spring Boot)**: [저장소 링크](https://github.com/CAPSTONE-DBFIS/server.git) - 사용자 인증(JWT), 회원 관리, 팀 생성 및 관리, 팀 파일 클라우드 관련 로직 등 핵심 비즈니스 로직과, 뉴스 분석 데이터(언급량, 감성 분포 등)를 시각화 대시보드에 제공하는 API를 담당합니다.
-   **데이터 수집 파이프라인 (Python Scripts & Jenkins)**: [저장소 링크](https://github.com/CAPSTONE-DBFIS/global-it-news-analysis.git) - Jenkins 파이프라인을 통해 주기적으로 국내외 IT 뉴스를 수집, 분석(키워드/감성)하고 데이터베이스(Elasticsearch, PostgreSQL)에 저장하는 데이터 수집 및 처리 자동화 스크립트입니다.

---

## 5. ⚙️ 시스템 아키텍처 및 데이터 파이프라인

<p align="center">
  <img src=".github/assets/system_architecture.png" width="700" alt="TRENDB System Architecture">
</p>

> TRENDB가 사용하는 핵심 데이터는 별도의 자동화된 파이프라인을 통해 구축됩니다. **Jenkins**를 사용하여 매일 스케줄링된 작업을 실행, 국내외 IT 뉴스를 자동으로 크롤링합니다. 수집된 각 기사는 다음과 같은 과정을 거쳐 처리됩니다.
> 1.  **키워드 추출**: 기사 제목의 핵심 키워드와 함께 등장하는 연관 키워드를 추출합니다.
> 2.  **감성 분석**: **`klue/bert-base`** 모델을 사용하여 기사 제목의 긍정/중립/부정 감성을 분석합니다.
> 3.  **데이터 저장**: 분석된 **감성 결과와 기사 본문**은 검색 및 집계를 위해 **Elasticsearch**에 함께 인덱싱됩니다. 추출된 **키워드와 그 빈도**는 시계열 트렌드 분석을 위해 **PostgreSQL**에 저장됩니다.


### 응답 처리 흐름
<p align="center">
  <img src=".github/assets/flow_chart.png" width="90%" alt="TRENDB 응답 처리 흐름도">
</p>

1.  **API 요청 (`/agent/query`)**: 사용자가 질문과 함께 파일, 페르소나 ID 등을 FastAPI 서버로 전송합니다.
2.  **컨텍스트 준비 (`AgentChatService`)**:
    - `get_session_history`: PostgreSQL에서 이전 대화 기록을 로드하여 `ConversationBufferWindowMemory`에 주입합니다.
    - `get_user_persona`: 사용자가 선택한 페르소나 정보를 DB에서 조회합니다.
    - `extract_text_by_filename`: 업로드된 파일이 있는 경우, 텍스트를 추출하여 메모리에 추가합니다.
3.  **에이전트 초기화**: 시스템 프롬프트, 메모리, 그리고 15+개의 도구(`tools`)를 결합하여 `AgentExecutor`를 생성합니다. LLM은 사용자가 선택한 모델로 동적으로 초기화됩니다.
4.  **자율적 도구 실행**:
    - 에이전트가 질문을 분석하여 `domestic_news_search_tool`, `trend_report_tool` 등 필요한 도구를 하나 이상 선택하여 실행합니다.
    - 도구 실행 로그는 SSE(Server-Sent Events)를 통해 클라이언트로 실시간 스트리밍됩니다.
5.  **결과 종합 및 최종 응답 생성**:
    - 도구 실행 결과를 종합하여 최종 답변을 생성합니다.
    - 생성된 답변 토큰과 함께, 도구 결과에서 추출된 관련 링크(출처) 정보도 SSE를 통해 스트리밍됩니다.
6.  **DB 저장**: 최종 응답이 완료되면 `save_chat_to_db`를 통해 대화 내용을 PostgreSQL에 저장합니다.

---

## 6. API 엔드포인트

| HTTP Method | 경로 | 설명 |
|---|---|---|
| `POST` | `/agent/query` | AI 에이전트에게 질문하고 스트리밍 응답을 받습니다. |
| `POST` | `/team-files` | 팀 파일을 업로드하고 Milvus에 벡터 임베딩을 저장합니다. |
| `DELETE` | `/team-files/{team_id}/{file_id}` | 특정 팀 파일과 관련된 벡터 임베딩을 삭제합니다. |
| `POST` | `/team-file/query` | 팀 파일 기반으로 RAG 질의응답을 수행합니다. |

---

## 7. 브랜치 전략

- **`main`**: 안정화된 최종 버전이 관리되는 브랜치입니다. GitHub Actions와 연동되어 `main` 브랜치에 병합 시 자동으로 배포가 진행됩니다.
- **`develop`**: 다음 출시 버전을 개발하는 브랜치입니다. 기능 개발이 완료되면 `feature` 브랜치에서 `develop`으로 병합됩니다.
- **`feature/*`**: 신규 기능 개발 및 버그 수정을 위한 브랜치입니다. `develop`에서 분기하며, 개발 완료 후 다시 `develop`으로 Pull Request를 보냅니다.