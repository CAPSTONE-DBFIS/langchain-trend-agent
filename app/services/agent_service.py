from fastapi import Request
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain.prompts import MessagesPlaceholder
from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler
from datetime import datetime
import json
import re

from app.tools.tools import tools
from app.utils.db_util import get_session_history, get_user_persona
from app.utils.db_util import save_chat_to_db  # DB 저장 유틸 함수가 있다고 가정

class AgentChatService:
    @staticmethod
    async def stream_response(query: str, chat_room_id: str, member_id: str):
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)

        memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="chat_history",
            output_key="output"
        )

        chat_history = get_session_history(chat_room_id)
        persona_prompt = get_user_persona(member_id)

        for msg in chat_history.messages:
            if isinstance(msg, HumanMessage):
                memory.chat_memory.add_user_message(msg.content)
            elif isinstance(msg, AIMessage):
                memory.chat_memory.add_ai_message(msg.content)

        current_datetime = datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""당신은 DB FIS 임직원들에게 업계 트렌드 정보를 제공하는 챗봇 TRENDB입니다. 반드시 아래 지침을 따르세요.
            ... (중략) ...
            유저 페르소나: {persona_prompt}
            현재 시간: {current_datetime}
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        callback = AsyncIteratorCallbackHandler()
        for tool in tools:
            tool.callbacks = [callback]

        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            memory=memory,
            callbacks=[callback],
            verbose=True,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
            name="AgentExecutor"
        )

        final_response = ""

        # 사용자 질의 후속 질문 파싱 함수
        def parse_gpt_output(raw_output: str):
            parts = raw_output.strip().split("다음 질문 추천:")
            answer = parts[0].strip()
            follow_ups = []

            if len(parts) > 1:
                follow_raw = parts[1].strip().split("\n")
                for line in follow_raw:
                    # '1. 질문내용', '2. 질문내용' 형태만 제거
                    clean_line = re.sub(r'^\d+\.\s*', '', line).strip()
                    if clean_line:
                        follow_ups.append(clean_line)

            return answer, follow_ups[:3]

        async def event_generator():
            nonlocal final_response
            final_sent = False
            try:
                async for event in executor.astream_events({"input": query}, version="v1"):
                    kind = event.get("event")
                    name = event.get("name")
                    data = event.get("data", {})

                    if kind == "on_chat_model_stream":
                        chunk = data.get("chunk", {})
                        token = chunk.get("content", "") if isinstance(chunk, dict) else getattr(chunk, "content", "")
                        if token:
                            final_response += token
                            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

                    elif kind == "on_text":
                        thought = data.get("text", "")
                        if thought:
                            yield f"data: {json.dumps({'log': thought}, ensure_ascii=False)}\n\n"

                    elif kind == "on_tool_start":
                        yield f"data: {json.dumps({'tool_start': f'{name} 호출', 'input': data.get('input', {})}, ensure_ascii=False)}\n\n"

                    elif kind == "on_chain_end" and name == "AgentExecutor" and not final_sent:
                        output = data.get("output", {}).get("output", "")
                        if output:
                            final_response = output  # 덮어쓰기 (최종 output이 더 정확)
                            yield f"data: {json.dumps({'final': output}, ensure_ascii=False)}\n\n"
                            final_sent = True

                    elif kind == "on_agent_action":
                        thought = data.get("action", {}).get("log", "")
                        if thought:
                            yield f"data: {json.dumps({'log': thought}, ensure_ascii=False)}\n\n"

                    elif kind == "on_tool_end":
                        observation = data.get("output", "")
                        if observation:
                            yield f"data: {json.dumps({'log': f'결과: {observation}'}, ensure_ascii=False)}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        async def streaming_with_db():
            async for chunk in event_generator():
                yield chunk
            if final_response.strip():
                save_chat_to_db(query=query, response=final_response, chat_room_id=chat_room_id, member_id=member_id)

        return StreamingResponse(streaming_with_db(), media_type="text/event-stream; charset=utf-8")