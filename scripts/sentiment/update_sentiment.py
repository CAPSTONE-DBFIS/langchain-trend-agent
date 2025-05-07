import os
import sys
import logging
import argparse
from datetime import datetime
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import numpy as np
import gc
import time

# psutil 패키지가 있는지 확인
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

"""
뉴스 기사 감정 분석 처리 스크립트

이 스크립트는 Elasticsearch에 저장된 뉴스 기사의 제목을 분석하여 감정(sentiment) 필드를 업데이트합니다.
기본적으로 테스트 모드로 실행되며, 감정 필드가 없는 문서만 처리합니다.

사용법:
1. 테스트 모드 (2개 문서만 처리): python update_sentiment.py
2. 특정 개수 처리: python update_sentiment.py --count 100
3. 모든 문서 처리: python update_sentiment.py --full
4. 배치 크기 지정: python update_sentiment.py --batch 200
5. 확인 없이 실행: python update_sentiment.py --full --force

주의:
- 18,000개 이상의 문서를 처리할 때는 메모리 사용량에 주의하세요.
- --full 옵션으로 실행하면 감정 필드가 없는 모든 문서가 처리됩니다.
"""


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
    def __init__(self, model_path="my_finetuned_bert1"):
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
                print(f"총 분석할 문서 수: {total_available}개")
                print(f"배치 크기: {batch_size}개 (약 {total_available // batch_size + 1}개의 배치)")

                # 대량 문서 처리 시 배치 크기 조정 제안
                if total_available > 5000 and batch_size < 200:
                    adjust = input(f"18,000개 이상의 기사를 처리하기 위해 배치 크기를 200으로 늘릴까요? (y/n): ")
                    if adjust.lower() == 'y':
                        batch_size = 200
                        print(f"배치 크기가 {batch_size}로 조정되었습니다.")

                confirm = input(f"총 {total_available}개 문서 중 {total_docs}개를 처리합니다. 계속하시겠습니까? (y/n): ")
                if confirm.lower() != 'y':
                    self.logger.info("사용자에 의해 작업이 취소되었습니다.")
                    return 0

            self.logger.info(f"감정 분석할 문서 수: {total_docs}")

            # 처리 계수 초기화
            processed = 0
            updated = 0
            skipped = 0
            start_time = datetime.now()
            last_progress_time = start_time
            last_memory_check = start_time
            last_memory_optimize = start_time

            # 처리할 문서 ID 기록 (안전장치)
            processed_ids = set()

            # 초기 리소스 상태 확인
            resources = get_system_resources()
            self.logger.info(f"초기 메모리 사용량: {resources['memory_used_mb']:.1f}MB, CPU: {resources['cpu_percent']:.1f}%")

            # 문서가 있는 동안 반복
            while processed < total_docs:
                # 주기적 메모리 최적화 (5분마다)
                current_time = datetime.now()
                if (current_time - last_memory_optimize).seconds > 300:
                    self.logger.info("메모리 최적화 실행...")
                    optimize_memory()
                    last_memory_optimize = current_time
                    resources = get_system_resources()
                    self.logger.info(f"최적화 후 메모리 사용량: {resources['memory_used_mb']:.1f}MB")

                # 매번 감정 필드가 없는 문서를 새로 검색 (다른 프로세스에서 업데이트했을 수 있음)
                response = es.search(index=ES_INDEX, body=query)
                hits = response["hits"]["hits"]

                if not hits:
                    self.logger.info("처리할 문서가 더 이상 없습니다.")
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
                        skipped += 1
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
                            skipped += 1
                            if processed >= total_docs:
                                break
                            continue

                    # 문서 업데이트
                    update_body = {
                        "doc": {
                            "sentiment": sentiment_result["sentiment"],
                            "sentiment_confidence": sentiment_result["confidence"]
                        }
                    }

                    try:
                        es.update(index=ES_INDEX, id=doc_id, body=update_body)
                        updated += 1

                        # 테스트 모드가 아닐 경우 로그 레벨을 낮춤 (너무 많은 로그 방지)
                        if max_docs and max_docs <= 10:
                            self.logger.info(f"문서 ID {doc_id} 업데이트 완료: {sentiment_result['sentiment']}")
                        else:
                            self.logger.debug(f"문서 ID {doc_id} 업데이트 완료: {sentiment_result['sentiment']}")
                    except Exception as e:
                        self.logger.error(f"문서 ID {doc_id} 업데이트 오류: {str(e)}")
                        skipped += 1

                    processed += 1

                    # 진행 상황 표시 (100개마다 또는 10초마다)
                    current_time = datetime.now()
                    if processed % 100 == 0 or (current_time - last_progress_time).seconds >= 10:
                        elapsed = (current_time - start_time).total_seconds()
                        docs_per_second = processed / elapsed if elapsed > 0 else 0
                        remaining_docs = total_docs - processed
                        estimated_time = remaining_docs / docs_per_second if docs_per_second > 0 else 0

                        print(f"진행 상황: {processed}/{total_docs} ({processed / total_docs * 100:.1f}%) - "
                              f"업데이트: {updated}, 건너뜀: {skipped}, 처리 속도: {docs_per_second:.1f}개/초, "
                              f"예상 남은 시간: {estimated_time / 60:.1f}분")
                        last_progress_time = current_time

                    # 리소스 모니터링 (1분마다)
                    if (current_time - last_memory_check).seconds >= 60:
                        resources = get_system_resources()
                        self.logger.info(
                            f"리소스 상태 - 메모리: {resources['memory_used_mb']:.1f}MB ({resources['memory_percent']:.1f}%), "
                            f"CPU: {resources['cpu_percent']:.1f}%")
                        last_memory_check = current_time

                    # 최대 문서 수 도달 시 중단
                    if processed >= total_docs:
                        break

                # 배치 처리 후 잠시 쉬기 (시스템 부하 감소)
                if max_docs is None or max_docs > 100:
                    time.sleep(0.5)

            # 최종 결과 보고
            elapsed_time = (datetime.now() - start_time).total_seconds()
            resources = get_system_resources()

            self.logger.info(f"감정 분석 완료: 총 {processed} 문서 중 {updated} 문서 업데이트됨, {skipped} 문서 건너뜀")
            self.logger.info(f"총 소요 시간: {elapsed_time / 60:.1f}분 (평균 {processed / elapsed_time:.1f}개/초)")
            self.logger.info(f"최종 메모리 사용량: {resources['memory_used_mb']:.1f}MB ({resources['memory_percent']:.1f}%)")
            return updated

        except Exception as e:
            self.logger.error(f"Elasticsearch 문서 처리 오류: {str(e)}")
            raise


# 시스템 리소스 모니터링 함수
def get_system_resources():
    """시스템 리소스 사용량을 반환합니다."""
    if not HAS_PSUTIL:
        return {"memory_used_mb": 0, "memory_percent": 0, "cpu_percent": 0}

    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)
        memory_percent = process.memory_percent()

        return {
            "memory_used_mb": memory_info.rss / (1024 * 1024),
            "memory_percent": memory_percent,
            "cpu_percent": cpu_percent
        }
    except Exception:
        return {"memory_used_mb": 0, "memory_percent": 0, "cpu_percent": 0}


# 메모리 최적화 함수
def optimize_memory():
    """메모리 사용량을 최적화합니다."""
    gc.collect()
    torch.cuda.empty_cache() if torch.cuda.is_available() else None


def main():
    try:
        # 명령줄 인수 처리
        parser = argparse.ArgumentParser(description='뉴스 기사 감정 분석 도구')
        parser.add_argument('--full', action='store_true', help='모든 문서 처리 (테스트 모드 비활성화)')
        parser.add_argument('--count', type=int, default=2, help='처리할 최대 문서 수 (기본값: 2)')
        parser.add_argument('--batch', type=int, default=100, help='배치 크기 (기본값: 100)')
        parser.add_argument('--force', action='store_true', help='확인 메시지 없이 진행')

        args = parser.parse_args()

        test_mode = not args.full
        max_docs = None if args.full else args.count
        batch_size = args.batch
        force_run = args.force

        # 모드 정보 출력
        mode_info = "테스트 모드" if test_mode else "전체 모드"
        doc_info = f"최대 {max_docs}개 문서" if max_docs else "모든 문서"
        batch_info = f"배치 크기: {batch_size}"

        print(f"실행 모드: {mode_info}, 처리할 문서: {doc_info}, {batch_info}")

        # 안전 확인
        if not test_mode and not force_run:
            confirm = input("테스트 모드가 아닌 전체 모드로 실행합니다. 계속하시겠습니까? (y/n): ")
            if confirm.lower() != 'y':
                print("작업이 취소되었습니다.")
                return 0

        analyzer = SentimentAnalyzer()
        updated_count = analyzer.update_elasticsearch_documents(batch_size=batch_size, max_docs=max_docs)
        print(f"감정 분석 완료: {updated_count}개 문서 업데이트됨")
        return 0
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 