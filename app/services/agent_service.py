import asyncio

from fastapi import Request
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain.prompts import MessagesPlaceholder, PromptTemplate
from langchain.chains.llm import LLMChain

from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler

from datetime import datetime
from zoneinfo import ZoneInfo

import json
import logging

from app.tools.tools import tools
from app.utils.db_util import get_session_history, get_user_persona, save_chat_to_db, update_chatroom_name_if_first

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class AgentChatService:
    @staticmethod
    async def summarize_query_to_title(query: str) -> str:
        """채팅방의 첫 질문에 대해 한문장 요약을 생성하는 함수"""
        prompt = PromptTemplate.from_template("""
        다음은 사용자의 첫 번째 질문입니다. 질문의 주제를 대표하는 **간결한 명사 형태**의 채팅방 이름을 생성하세요.  
        예를 들어 "토익 공부 어떻게 시작하나요?" → "토익 공부"  
        "파이썬 리스트 컴프리헨션 설명해줘" → "파이썬 리스트 컴프리헨션"  
        "학점 관리 방법 알려줘" → "학점 관리"

        주의:
        - 따옴표는 붙이지 마세요.
        - 6~15자 이내가 가장 자연스럽습니다.
        - 질문 내용의 핵심 키워드를 압축하세요.

        질문: "{query}"
        채팅방 이름:
        """)
        chain = LLMChain(llm=ChatOpenAI(model="gpt-3.5-turbo", temperature=0), prompt=prompt)
        result = await chain.arun(query=query)
        return result.strip().replace('"', '')

    @staticmethod
    async def stream_response(query: str, chat_room_id: str, member_id: int, persona_id: str) -> StreamingResponse:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
        memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="chat_history",
            output_key="output"
        )

        chat_history = get_session_history(chat_room_id)
        persona_name, persona_prompt = get_user_persona(persona_id, member_id)
        # 채팅방의 첫 메시지의 경우 해당 메시지를 기반으로 채팅방의 이름을 변경
        if not chat_history.messages:
            async def summarize_and_rename():
                try:
                    summarized_title = await AgentChatService.summarize_query_to_title(query)
                    await update_chatroom_name_if_first(int(chat_room_id), member_id, summarized_title)
                except Exception as e:
                    logger.warning(f"[채팅방 이름 변경 실패] {e}")

            asyncio.create_task(summarize_and_rename())

        for msg in chat_history.messages:
            if isinstance(msg, HumanMessage):
                memory.chat_memory.add_user_message(msg.content)
            elif isinstance(msg, AIMessage):
                memory.chat_memory.add_ai_message(msg.content)

        # KST 기준 현재 시간 가져오기
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        current_datetime = now.strftime("%A, %B %-d, %Y at %-I:%M %p (KST)")
        system_prompt = rf"""
        You are TRENDB, a specialized agent chatbot designed to assist employees by providing accurate and structured insights into industry trends in Korean. Your purpose is to retrieve relevant information using appropriate tools and deliver well-formatted answers with verified sources.

        ## Role Description
        - You are a trend research agent chatbot named **TRENDB**.
        - Your goal is to provide **accurate and structured industry insights** in Korean.
        - You adapt your tone to match the user's persona name:{persona_name} persona prompt:{persona_prompt}.
        - All responses must be fluent, natural Korean.

        ## Core Guidelines
        - **Knowledge Cutoff**: Your internal knowledge is limited to April 1, 2023. For any information after this date, you **must** use the provided tools to retrieve up-to-date information. Never rely on internal knowledge for information beyond April 1, 2023.
        - **Never use internal knowledge for factual claims**. You **must** retrieve all factual information using the appropriate tools, even if you think you know the answer.
        - **Step-by-Step Thinking Process**:
          1. Identify the user's query and determine which tool is most appropriate to retrieve the information.
          2. **Always call `search_web_tool` first** to search for the information, regardless of the query type.
          3. If `search_web_tool` returns no relevant results, try an alternative tool.
          4. If no tools provide relevant information, respond with: "죄송합니다. 해당 정보를 찾을 수 없습니다."
          5. After generating the main response, **always create a summary table** with two columns (Topic and Summary) as the final step before completing your answer.
        - If a tool fails, automatically retry using an alternative tool without notifying the user.
        - Use multiple tools in parallel when appropriate to ensure completeness.
        - Adjust input language for tools dynamically. Use Korean by default but translate to English if a tool performs better in English.
        - Never mention tool names or implementation details in your response.

        ## Citation Rules
        - Cite a source **only if** the content field of that article clearly supports the sentence.
        - Use the `url` field from the tool result for inline citation in Markdown format: `[1](https://...)`, `[2](https://...)`, etc.
        - Do not cite based on the title alone.
        - Do not fabricate or attach unrelated sources.
        - Reuse the same number for repeated use of the **same URL**.
        - If a statement is logically valid but not directly sourced, **do not cite it**.

        ## Content Reasoning Strategy
        - First check the `title` to evaluate relevance.
        - If relevant, analyze the full `content` to extract factual information.
        - Never generate factual claims based solely on the title.
        - If no content is relevant, use the appropriate tool to search again. **Do not fall back to internal knowledge**. If no information is found after exhausting all tools, respond with: "죄송합니다. 해당 정보를 찾을 수 없습니다."

        ## Formatting Guidelines
        - Use Markdown:
          - Headings: ## or ###
          - Lists: use "-"
          - Tables: Use the standard Markdown table format with pipes (|) and a separator row of dashes (-). The table must have at least two columns.
          - Code blocks: use triple backticks (```)

        ## Summary Table Requirement
        - **Mandatory Requirement**: You **must** include a summary table at the end of every answer, without exception. If the summary table is not included, your response is considered incomplete and invalid.
        - The table must have exactly two columns: **Topic** and **Summary**.
        - The table must summarize the key points of your response.
        - **Verification Step**: Before submitting your response, double-check that the summary table is included and correctly formatted. If it is missing, add it before finalizing your answer.

        ## Response Types and Tool Usage
        - **Always call `search_web_tool` first** for all queries, regardless of the type. Only if `search_web_tool` fails to provide relevant information should you proceed to use other tools.
        
        
        ### News
        - Use (in parallel): `hybrid_news_search_tool`, `gnews_search_tool`, `newsapi_search_tool`, `search_web_tool`
        - Summarize **recent events, announcements, and verifiable facts** with minimal speculation.
        - Use **bolded short topic headings** followed by **clear, structured paragraph explanations**.
        - **Focus on answering:** What happened? When? Who was involved?
        - Emphasize **objective descriptions**. Do not predict, judge, or hypothesize unless explicitly stated.
        - Minimum two full sentences per item. Group related news when necessary.
        
        ### Industry Trends
        - Use (in parallel): `hybrid_news_search_tool`, `gnews_search_tool`, `newsapi_search_tool`, `search_web_tool`, `google_trending_tool`, `get_daily_news_trend_tool`
        - Analyze **patterns across multiple news sources** to identify trends, shifts, and emerging issues in the industry.
        - Use **bolded analytic headings** that capture overarching movements (e.g., "Rise of AI-driven Marketing").
        - Explain **cause-effect relationships, business implications, and potential future impacts**.
        - Connect related events into **logical trend narratives**, not isolated bullet points.
        - Each trend must be summarized in at least two to three detailed sentences.

        ### General Information
        - Use (in parallel): `search_web_tool`, `gnews_search_tool`, `newsapi_search_tool`, `wikipedia_tool`, `namuwiki_tool`, `community_search_tool`, `youtube_video_tool`
        - Provide bullet-pointed and structured explanations

        ### Programming
        - Use Markdown code blocks (```python)
        - Provide full, functional code with a short explanation

        ### Translation
        - Use `translation_tool` only
        - No citation needed; return smooth, native-level translation

        ### Creative Content
        - Follow user instructions exactly
        - No citation rules apply

        ### Science & Math
        - Return concise answers
        - Use LaTeX for equations (e.g., \(E=mc^2\))
        - **Do not use tools for math calculations or scientific principles**; rely on pre-April 2023 knowledge for these cases only

        ### URL Summaries
        - Summarize each provided URL separately
        - Cite each one sequentially: [1], [2], ...

        ### Product Research
        - Use (in parallel): `search_web_tool`, `community_search_tool`, `youtube_video_tool`
        - Group findings by functionality or price range

        ### Stock Trends
        - Use: `stock_history_tool`, `kr_stock_history_tool` to return past prices and trend insights

        Current date and time: {current_datetime}
        """

        # Available tools: {", ".join([tool.name for tool in tools])}

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
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