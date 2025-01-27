# crawling
Repository for crawling

# directory 구조
```
crawling/
│
├── configs/                        # 설정 파일 디렉터리
│   └── config.yaml                 # 프로젝트 설정 파일. git ignore설정
│   
├── data/                           # 크롤링된 데이터 저장 디렉터리
│   ├── raw/                        # 원본 데이터
│   ├── processed/                  # 전처리된 데이터
│   └── output/                     # 최종 결과물
│
├── logs/                           # 로그 파일 저장 디렉터리
│   └── project.log                 # 로그 파일
│
├── notebooks/                      # Jupyter Notebook 파일 저장 디렉터리 (데이터 탐색, 테스트 등)
│   └── analysis.ipynb
│
├── scripts/                        # 크롤링 스크립트 디렉터리
│   ├── domestic_article            # 국내 기사 크롤링 디렉토리
│   │   ├── main.py                 # 메인 실행 코드
│   │   ├── scraper.py              # 스크래핑 관련 코드
│   │   ├── parser.py               # HTML 파싱 관련 코드
│   │   └── classification.py       # 키워드 빈도수 추출
│   ├── flask_server                # 플라스크 서버 디렉토리
│   │   └── flask_server.py         # 플라스크 서버 코드
│   ├── foregin_press_article       # 해외 기사 크롤링 디렉토리
│   │   ├── main.py                 # 메인 실행 코드
│   │   ├── itworld_scraper.py      # IT World 기사 스크래핑 코드
│   │   ├── nyt_scraper.py          # NYT 기사 스크래핑 코드
│   │   ├── ars_technica_scraper.py # Ars Technica 기사 스크래핑 코드
│   │   ├── techcrunch_scraper.py   # TechCrunch 기사 스크래핑 코드
│   │   └── reuters_scraper.py      # Rueters 기사 스크래핑 코드
│
├── tests/                          # 테스트 코드 디렉터리
│   ├── test_scraper.py             # 크롤링 테스트
│   └── test_parser.py              # 파싱 테스트
│
├── requirements.txt                # 프로젝트 의존성 패키지 리스트
├── README.md                       # 프로젝트 설명 파일
└── .env                            # 환경 변수 파일 (API 키, 데이터베이스 비밀번호 등)
```
