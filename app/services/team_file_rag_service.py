from fastapi.responses import StreamingResponse
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler
from langchain_openai import ChatOpenAI
from app.utils.milvus_util import get_team_file_vector_store
import json, asyncio

class TeamFileRAGService:
    """팀 공유 문서를 기반으로 스트리밍 응답을 생성하는 RAG 서비스"""

    @staticmethod
    async def stream_team_file_response(team_id: str, query: str) -> StreamingResponse:
        """
        팀 ID와 질의를 받아 Milvus에서 문서를 검색하고,
        해당 문서를 기반으로 LLM의 답변을 스트리밍 형식으로 반환한다.
        """

        # team_id 필터 조건으로 벡터 리트리버 설정
        vs = get_team_file_vector_store()
        retriever = vs.as_retriever(
            search_kwargs={"filter": {"team_id": team_id}, "top_k": 5}
        )

        # RAG 응답에 사용할 시스템 프롬프트
        system_template = """
        You are a helpful assistant that only uses the team's shared documents to answer.
        Do not cite sources in your response.
        Your response will be streamed, and sources will be displayed separately.
        Please answer in Korean.
        """.strip()

        prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=system_template + "\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"
        )

        # LLM 토큰 스트리밍을 위한 비동기 콜백 핸들러 구성
        callback = AsyncIteratorCallbackHandler()

        # GPT-4o-mini 모델을 스트리밍 모드로 초기화
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            streaming=True,
            callbacks=[callback],
            temperature=0
        )

        # RetrievalQA 체인 구성 (context 기반 질의응답)
        qa = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt},
        )

        # SSE 방식으로 응답을 전송하는 스트리밍 제너레이터 정의
        async def token_stream():
            task = asyncio.create_task(qa.ainvoke({"query": query}))

            async for token in callback.aiter():
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            result = await task
            source_docs = result.get("source_documents", [])

            # 파일명 추출
            source_names = []
            for doc in source_docs:
                meta = doc.metadata or {}
                name = meta.get("file_name") or meta.get("fileName") or meta.get("source")
                if name:
                    source_names.append(name)

            if source_names:
                yield f"data: {json.dumps({'sources': list(set(source_names))}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        # StreamingResponse 객체 반환
        return StreamingResponse(token_stream(), media_type="text/event-stream; charset=utf-8")