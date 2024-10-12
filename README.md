# crawling
Repository for crawling

# directory 구조
crawling/
│
├── configs/            # 설정 파일 디렉터리
│   └── config.yaml     # 프로젝트 설정 파일. git ignore설정
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
│   └── analysis.ipynb
│
├── scripts/            # 크롤링 스크립트 디렉터리
│   ├── main.py         # 메인 실행 파일
│   ├── scraper.py      # 스크래핑 관련 코드
│   └── parser.py       # HTML 파싱 관련 코드
│
├── tests/              # 테스트 코드 디렉터리
│   ├── test_scraper.py # 크롤링 테스트
│   └── test_parser.py  # 파싱 테스트
│
├── requirements.txt    # 프로젝트 의존성 패키지 리스트
├── README.md           # 프로젝트 설명 파일
└── .env                # 환경 변수 파일 (API 키, 데이터베이스 비밀번호 등)
