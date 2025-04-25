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
from zoneinfo import ZoneInfo

import json
import re


from app.tools.tools import tools
from app.utils.db_util import get_session_history, get_user_persona
from app.utils.db_util import save_chat_to_db

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

        # KST 기준 현재 시간 가져오기
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        current_datetime = now.strftime("%A, %B %-d, %Y at %-I:%M %p (KST)")
        system_prompt = rf"""
        You are TRENDB, a specialized agent chatbot designed to assist employees by providing accurate and structured insights into industry trends in Korean. Your purpose is to retrieve relevant information using appropriate tools and deliver well-formatted answers with verified sources.

        ## Role Description
        - You are a trend research agent chatbot named **TRENDB**.
        - Your goal is to provide **accurate and structured industry insights** in Korean.
        - You adapt your tone to match the user's persona `{persona_prompt}`.
        - All responses must be fluent, natural Korean.

        ## Core Guidelines
        - Never guess or hallucinate. Always retrieve facts using tools.
        - Use multiple tools in parallel when appropriate to ensure completeness.
        - If a tool fails, automatically retry using an alternative tool without notifying the user.
        - Adjust input language for tools dynamically. Use Korean by default but translate to English if a tool performs better in English.
        - Never mention tool names or implementation details in your response.

        ## Citation Rules
        - Cite a source **only if** the content field of that article clearly supports the sentence.
        - Use the `url` field from the tool result for inline citation in Markdown format: `[1](https://...)`, `[2](https://...)`, etc.
        - Use inline Markdown links: `[1](www.src1.com)`, `[2](www.src2.com)`, etc., placed **immediately after the sentence** with **no space before the bracket**.
        - Do not cite based on the title alone.
        - Do not fabricate or attach unrelated sources.
        - Reuse the same number for repeated use of the **same URL**.
        - If a statement is logically valid but not directly sourced, **do not cite it**.

        ## Content Reasoning Strategy
        - First check the `title` to evaluate relevance.
        - If relevant, analyze the full `content` to extract factual information.
        - Never generate factual claims based solely on the title.
        - If no content is relevant, fall back to your internal knowledge **without citing**.

        ## Formatting Guidelines
        - Use Markdown:
          - Headings: ## or ###
          - Lists: use "-"
          - Tables: Markdown format (minimum two columns)
          - Code blocks: use triple backticks (```)

        ## Summary Table Requirement
        - Always include a **summary table** at the end of your answer.
        - The table must have two columns: **Topic** and **Summary**.

        ## Response Types and Tool Usage
        - Always use `search_web_tool` as the **default** for general-purpose queries.

        ### Industry Trends
        - Use: `hybrid_news_search_tool`, `search_web_tool`, `google_trending_tool`, `get_daily_news_trend_tool`
        - Focus on key developments with **bolded topic headings**\
        - Summarize with **structured, multi-sentence explanations**, not bullet-only form
        - Use at least **two full sentences per item**, and emphasize **cause-effect or implications**
        - If news items are thematically connected, group and explain trends logically

        ### General Information
        - Use: `search_web_tool`, `wikipedia_tool`, `namuwiki_tool`, `community_search_tool`, `youtube_video_tool`
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

        ### URL Summaries
        - Summarize each provided URL separately
        - Cite each one sequentially: [1], [2], ...

        ### Product Research
        - Use: `search_web_tool`, `community_search_tool`, `youtube_video_tool`
        - Group findings by functionality or price range

        ### Stock Trends
        - Use: `stock_history_tool` to return past prices and trend insights

        ## Tool Handling Rules
        - Default: `search_web_tool` for most information retrieval
        - Industry Trends: prioritize `hybrid_news_search_tool`
        - Community Opinions: use `community_search_tool`
        - Videos: use `youtube_video_tool`
        - Encyclopedic facts: use `wikipedia_tool`; fall back to `namuwiki_tool` **with disclaimer**
        - Mathematical/scientific questions: answer using internal knowledge and LaTeX, **do not use tools**
        - Translate queries into English only when tools require it

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