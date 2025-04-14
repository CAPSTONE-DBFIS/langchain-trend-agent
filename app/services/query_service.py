# import time
# import os
# from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI
# from langchain.prompts import PromptTemplate
# from langchain_core.runnables.history import RunnableWithMessageHistory
# from langchain_core.output_parsers import StrOutputParser
# from operator import itemgetter
# from app.utils.db import get_user_persona, get_session_history
# from app.utils.milvus import get_embedding_model, get_vector_store
#
# # 환경 변수 로드
# load_dotenv()
#
# # LLM 설정
# llm_model = ChatOpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     temperature=0,  # 창의성
#     model_name="gpt-4o-mini"
# )
#
# # 프롬프트 템플릿
# prompt_template = PromptTemplate.from_template(
# """당신은 DB FIS 임직원들에게 업계 트렌드 정보를 제공하는 챗봇 **TRENDB** 입니다.
# 당신의 임무는 **검색된 문서와 대화 기록을 참고하여** 사용자 질문에 답변하는 것입니다.
# (단, 기술 용어나 기업 이름은 번역하지 않고 원문 그대로 유지하세요.)
#
# ### 사용자 페르소나:
# {persona_prompt}
#
# ### 답변 방식:
# 1. **질문이 업계 트렌드 관련 질문인 경우:**
#    - **검색된 문서에서 관련 정보를 찾았다면:**
#      - "*[기사 제목]* (언론사, 날짜)에 따르면, 기사 내용 요약"
#      - 이런 형식으로 기사 내용을 인용하여 신뢰도 높은 답변을 제공하세요.
#    - **검색된 문서에서 답변을 찾지 못한 경우:**
#      - 대화 기록을 참고하여 **관련 정보를 찾을 수 있다면 이를 활용하여 답변하세요.**
#      - 이전 대화에서 언급된 내용을 바탕으로 자연스럽게 답변을 생성하세요.
#      - **검색된 문서와 대화 기록 어디에서도 답을 찾을 수 없는 경우에만, "해당 정보는 현재 제공된 데이터에서 찾을 수 없습니다."라고 답변하세요.**
#
# 2. **질문이 일반 대화(잡담, 인사, 피드백 등)인 경우:**
#    - 일반 대화에 자연스럽게 반응하세요.
#
# ### 참고 정보:
# DB FIS의 주요 경쟁사는 다음과 같습니다:
# 삼성SDS, LG CNS, 현대오토에버, SK C&C, 롯데정보통신, 포스코DX, 미라콤아이앤씨, 메가존클라우드, 한화시스템, CJ올리브네트웍스
#
# ### 대화 기록:
# {chat_history}
#
# ### 검색된 문서:
# {context}
#
# ### 사용자 질문:
# {question}
# """
# )
#
# # 체인 생성 (LLM 호출 흐름)
# query_pipeline = (
#         {
#             "question": itemgetter("question"),
#             "context": itemgetter("context"),
#             "chat_history": itemgetter("chat_history"),
#             "persona_prompt": itemgetter("persona_prompt")
#         }
#         | prompt_template
#         | llm_model
#         | StrOutputParser()
# )
#
# # RAG 체인 + 대화 이력 반영
# chatbot_pipeline = RunnableWithMessageHistory(
#     runnable=query_pipeline,
#     get_session_history=get_session_history,
#     input_messages_key="question",
#     history_messages_key="chat_history",
# )
#
# # 사용자 질의 처리 함수
# def process_user_query(chat_room_id, query, member_id):
#     try:
#         print(f"[DEBUG] chat_room_id: {chat_room_id}, query: {query}, member_id: {member_id}", flush=True)
#
#         start_time = time.time()  # 시간 측정 시작
#
#         # Embedding 모델 및 벡터 저장소 가져오기
#         embedding_model = get_embedding_model()
#         vector_store = get_vector_store()
#
#         # 페르소나 정보 가져오기
#         persona_prompt = get_user_persona(member_id)
#
#         print(f"[DEBUG] 불러온 persona_prompt: {persona_prompt}", flush=True)
#
#         # 사용자의 질문을 벡터로 변환
#         query_embedding = embedding_model.embed_query(query)
#         print(f"[DEBUG] Query embedding 생성 완료", flush=True)
#
#         # Milvus 벡터 검색
#         # 최신 문서 검색 (최근 30일 내)
#         recent_timestamp = int(time.time()) - (30 * 86400)  # 최근 30일 타임스탬프 기준
#         latest_results = vector_store.similarity_search_with_score_by_vector(
#             query_embedding, k=3, filter={"timestamp": {"$gte": recent_timestamp}}
#         )
#
#         # 최신 문서 중 점수 필터링
#         latest_results = [(doc, score) for doc, score in latest_results if score >= 250]
#
#         # 최신 문서가 3개 미만이면 기존 문서에서 추가 검색
#         if len(latest_results) < 3:
#             additional_results = vector_store.similarity_search_with_score_by_vector(query_embedding, k=5)
#             combined_results = latest_results + [doc for doc in additional_results if doc not in latest_results]
#         else:
#             combined_results = latest_results
#
#         # 최신 문서, 기존 문서 구분해서 프롬프트에 넣기
#         context = "\n\n".join([
#             f"[최신 문서] {doc.metadata['title']} ({doc.metadata['media_company']}, ({doc.metadata['date']})\n{doc.page_content}"
#             if doc in latest_results else
#             f"[기존 문서] {doc.metadata['title']} ({doc.metadata['media_company']}, ({doc.metadata['date']})\n{doc.page_content}"
#             for doc, _ in combined_results
#         ])
#         print(f"[DEBUG] 최종 context 생성 완료", flush=True)
#
#         input_data = {
#             "question": query,
#             "context": context,
#             "persona_prompt": persona_prompt
#         }
#
#         gpt_response = chatbot_pipeline.invoke(
#             input_data, config={"configurable": {"session_id": f"{chat_room_id}"}}
#         )
#
#         gpt_time = time.time() - start_time  # 시간 측정 종료
#         print(f"[DEBUG] GPT 응답 생성 완료, 소요 시간: {gpt_time:.4f}초", flush=True)
#
#         return {
#             "query": query,
#             "search_results": [
#                 {
#                     "title": doc.metadata["title"],
#                     "date": doc.metadata["date"],
#                     "media_company": doc.metadata["media_company"],
#                     "url": doc.metadata["url"],
#                     "score": score
#                 } for doc, score in combined_results
#             ],
#             "gpt_response": gpt_response
#         }
#
#     except Exception as e:
#         print(f"[ERROR] 쿼리 처리 중 오류 발생: {str(e)}", flush=True)
#         return {"error": f"서버 내부 오류: {str(e)}"}