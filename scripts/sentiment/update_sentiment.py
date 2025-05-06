import os
import sys
import logging
from datetime import datetime
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import numpy as np

# 로깅 설정
def setup_logger():
    # 로그 디렉토리 생성
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 로거 설정
    logger = logging.getLogger('sentiment_analyzer')
    logger.setLevel(logging.INFO)
    
    # 파일 핸들러 추가
    file_handler = logging.FileHandler(os.path.join(log_dir, 'sentiment.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 콘솔 핸들러 추가
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷 설정
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 환경변수 로드
load_dotenv()

# Elasticsearch 연결 설정
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "localhost")
ES_PORT = int(os.getenv("ELASTICSEARCH_PORT", "9200"))
ES_USER = os.getenv("ELASTICSEARCH_USERNAME", "")
ES_PASS = os.getenv("ELASTICSEARCH_PASSWORD", "")
ES_INDEX = os.getenv("ELASTICSEARCH_DOMESTIC_INDEX_NAME", "news_article")  # 뉴스 기사 인덱스명

# Elasticsearch 클라이언트 초기화
es = Elasticsearch(
    [{'host': ES_HOST, 'port': ES_PORT, 'scheme': 'http'}],
    basic_auth=(ES_USER, ES_PASS) if ES_USER and ES_PASS else None
)

# 안전 설정 - Elasticsearch 연결 확인
def check_es_connection():
    try:
        if not es.ping():
            return False, "Elasticsearch 서버에 연결할 수 없습니다."
        return True, "Elasticsearch 서버에 연결되었습니다."
    except Exception as e:
        return False, f"Elasticsearch 연결 오류: {str(e)}"

# 안전 설정 - 색인 존재 확인
def check_index_exists(index_name):
    try:
        if not es.indices.exists(index=index_name):
            return False, f"'{index_name}' 인덱스가 존재하지 않습니다."
        return True, f"'{index_name}' 인덱스가 확인되었습니다."
    except Exception as e:
        return False, f"인덱스 확인 오류: {str(e)}"

class SentimentAnalyzer:
    def __init__(self, model_path="scripts/sentiment/my_finetuned_bert1"):
        self.logger = setup_logger()
        self.logger.info("감정 분석기 초기화 시작")
        
        # GPU 사용 가능 여부 확인
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.logger.info(f"사용 중인 디바이스: {self.device}")
        
        try:
            # 모델 및 토크나이저 로드
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
            self.model.to(self.device)
            self.model.eval()
            self.logger.info("모델 로딩 완료")
        except Exception as e:
            self.logger.error(f"모델 로딩 오류: {str(e)}")
            raise
        
        # 감정 레이블 정의
        self.labels = ["negative", "neutral", "positive"]
    
    def analyze_text(self, text):
        """텍스트의 감정 분석을 수행합니다."""
        try:
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probabilities = torch.nn.functional.softmax(logits, dim=1)
                
            # 가장 확률이 높은 감정 클래스 선택
            predicted_class = torch.argmax(probabilities, dim=1).item()
            confidence = probabilities[0][predicted_class].item()
            
            sentiment = self.labels[predicted_class]
            
            return {
                "sentiment": sentiment,
                "confidence": confidence
            }
        except Exception as e:
            self.logger.error(f"감정 분석 오류: {str(e)}")
            return {"sentiment": "neutral", "confidence": 0.0}
    
    def update_elasticsearch_documents(self, batch_size=100, max_docs=2):  # 기본값을 2로 설정하여 테스트
        """Elasticsearch의 문서들을 감정 분석하여 업데이트합니다."""
        self.logger.info("Elasticsearch 문서 감정 분석 시작")
        
        try:
            # 안전 설정 검사
            conn_status, conn_msg = check_es_connection()
            if not conn_status:
                self.logger.error(conn_msg)
                return 0
            self.logger.info(conn_msg)
            
            index_status, index_msg = check_index_exists(ES_INDEX)
            if not index_status:
                self.logger.error(index_msg)
                return 0
            self.logger.info(index_msg)
            
            # 테스트 모드 정보 로깅
            if max_docs and max_docs <= 10:
                self.logger.info(f"테스트 모드: 최대 {max_docs}개 문서만 처리합니다.")
            
            # 감정 필드가 없는 문서 검색
            query = {
                "size": batch_size,
                "query": {
                    "bool": {
                        "must_not": [
                            {"exists": {"field": "sentiment"}}
                        ]
                    }
                }
            }
            
            # 처음 검색 실행하여 총 문서 수 파악
            response = es.search(index=ES_INDEX, body=query)
            total_available = response["hits"]["total"]["value"]
            
            if total_available == 0:
                self.logger.info("분석할 문서가 없습니다. 모든 문서에 이미 감정 필드가 존재합니다.")
                return 0
                
            total_docs = min(total_available, max_docs if max_docs is not None else total_available)
            
            # 실행 전 사용자 확인 (테스트 모드가 아닌 경우)
            if max_docs is None or max_docs > 10:
                confirm = input(f"총 {total_available}개 문서 중 {total_docs}개를 처리합니다. 계속하시겠습니까? (y/n): ")
                if confirm.lower() != 'y':
                    self.logger.info("사용자에 의해 작업이 취소되었습니다.")
                    return 0
                
            self.logger.info(f"감정 분석할 문서 수: {total_docs}")
            
            # 처리 계수 초기화
            processed = 0
            updated = 0
            
            # 처리할 문서 ID 기록 (안전장치)
            processed_ids = set()
            
            # 문서가 있는 동안 반복
            while processed < total_docs:
                response = es.search(index=ES_INDEX, body=query)
                hits = response["hits"]["hits"]
                
                if not hits:
                    break
                
                remaining = total_docs - processed
                current_batch_size = min(batch_size, remaining)
                
                for hit in hits[:current_batch_size]:
                    doc_id = hit["_id"]
                    
                    # 이미 처리한 문서인지 확인 (안전장치)
                    if doc_id in processed_ids:
                        continue
                        
                    processed_ids.add(doc_id)
                    doc = hit["_source"]
                    
                    # 제목이 있는지 확인
                    if not doc.get("title"):
                        self.logger.warning(f"문서 ID {doc_id}에 제목이 없습니다.")
                        processed += 1
                        if processed >= total_docs:
                            break
                        continue
                    
                    title = doc["title"]
                    
                    # 테스트 모드에서는 업데이트하기 전에 확인 메시지 출력
                    if max_docs and max_docs <= 10:
                        self.logger.info(f"분석할 제목: {title}")
                    
                    # 감정 분석 수행
                    sentiment_result = self.analyze_text(title)
                    
                    # 테스트 모드에서는 결과 출력 후 사용자 확인
                    if max_docs and max_docs <= 10:
                        self.logger.info(f"분석 결과: {sentiment_result}")
                        confirm = input(f"문서 ID {doc_id}의 감정을 '{sentiment_result['sentiment']}'로 업데이트하시겠습니까? (y/n): ")
                        if confirm.lower() != 'y':
                            self.logger.info(f"문서 ID {doc_id} 업데이트를 건너뜁니다.")
                            processed += 1
                            if processed >= total_docs:
                                break
                            continue
                    
                    # 문서 업데이트
                    update_body = {
                        "doc": {
                            "sentiment": sentiment_result["sentiment"]
                        }
                    }
                    
                    try:
                        es.update(index=ES_INDEX, id=doc_id, body=update_body)
                        updated += 1
                        self.logger.info(f"문서 ID {doc_id} 업데이트 완료: {sentiment_result['sentiment']}")
                    except Exception as e:
                        self.logger.error(f"문서 ID {doc_id} 업데이트 오류: {str(e)}")
                    
                    processed += 1
                    
                    # 최대 문서 수 도달 시 중단
                    if processed >= total_docs:
                        break
            
            self.logger.info(f"감정 분석 완료: 총 {processed} 문서 중 {updated} 문서 업데이트됨")
            return updated
            
        except Exception as e:
            self.logger.error(f"Elasticsearch 문서 처리 오류: {str(e)}")
            raise

def main():
    try:
        # 명령줄 인수 처리
        test_mode = True  # 기본값은 테스트 모드
        max_docs = 2  # 기본적으로 2개만 처리
        
        if len(sys.argv) > 1:
            if sys.argv[1] == '--full':
                test_mode = False
                max_docs = None
            elif sys.argv[1].isdigit():
                max_docs = int(sys.argv[1])
        
        # 모드 정보 출력
        mode_info = "테스트 모드" if test_mode else "전체 모드"
        doc_info = f"최대 {max_docs}개 문서" if max_docs else "모든 문서"
        print(f"실행 모드: {mode_info}, 처리할 문서: {doc_info}")
        
        # 안전 확인
        if not test_mode:
            confirm = input("테스트 모드가 아닌 전체 모드로 실행합니다. 계속하시겠습니까? (y/n): ")
            if confirm.lower() != 'y':
                print("작업이 취소되었습니다.")
                return 0
        
        analyzer = SentimentAnalyzer()
        updated_count = analyzer.update_elasticsearch_documents(max_docs=max_docs)
        print(f"감정 분석 완료: {updated_count}개 문서 업데이트됨")
        return 0
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 