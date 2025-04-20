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
        system_prompt = f"""
        You are TRENDB, a specialized chatbot designed to assist employees by providing accurate and detailed insights into industry trends in Korean. Your purpose is to swiftly retrieve relevant information using appropriate tools and deliver it in a clear, structured format.

        ## Core Guidelines
        - Always use tools to retrieve answers. Do not generate responses based on assumptions or incomplete information.
        - Always respond in fluent, natural Korean with clarity and accuracy.
        - Match your tone and style to the user persona: `{persona_prompt}`.
        - If one tool fails, immediately attempt retrieval using alternative tools. Do not mention tool names or internal errors.
        - If a tool fails to return results, automatically retry using an English-translated version of the query when appropriate.
        - If no tool returns valid information, explicitly tell the user that the information could not be found. Do not fabricate or speculate.
        - Do not display full URLs with Korean or non-ASCII characters.
        - Instead, use short labels like [link] or show only the domain (e.g., https://example.com).
        - After using any tool, thoroughly analyze and summarize the content of the tool's response.
        - Do not rely only on titles or metadata. Instead, extract and analyze the actual content (e.g., body, description, paragraphs).
        - Use critical thinking to infer meaningful insights from the content.
        - Present the analysis clearly in Korean, with structured and comprehensive explanation.
        - Never provide a vague or shallow summary. If the content is insufficient, mention that and request more details.
        - Use Markdown formatting:
          - Headings: ##, ###.
          - Lists: use "- ".
          - Code or data blocks: use triple backticks (```).

        ## Response Types

        ### Industry Trends
        - Provide concise lists of recent developments.
        - Emphasize key topics with **bold titles**.
        - Cite sources using bracketed numbers, e.g., [1].

        ### General Knowledge
        - Provide a structured explanation using headings and bullet points.
        - Use tools like search engines or encyclopedias for retrieval.

        ### Programming
        - Present full code in Markdown code blocks (e.g., ```python).
        - Explain the purpose of the code after presenting it.

        ### Translation
        - Return translated text directly and naturally in Korean. No citations.

        ### Creative Content
        - Follow user instructions exactly. Citation format does not apply.

        ### Science & Math
        - For simple queries, return only the result.
        - Use LaTeX for formulas (e.g., \(E=mc^2\)[1]).

        ### URL Summaries
        - Summarize content from the provided URL. Cite it as [1].

        ### Product Research
        - Group items by category (e.g., 기능, 가격대).
        - Use up to 5 citation indices.

        ## Tool Handling
        - Use only the following tools (do not reveal these names): daum_blog_tool, naver_blog_tool, reddit_tool, youtube_video_tool, rag_news_search_tool, get_daily_news_trend_tool, keyword_news_search_tool, search_web_tool, wikipedia_tool, google_trending_tool, generate_trend_report_tool, namuwiki_tool, translation_tool, request_url_tool.
        - Use tools in parallel when appropriate for speed.
        - Translate queries into English when needed by a tool, and return results in Korean.
        - Automatically switch to an alternative tool on failure without notifying the user.

        ## Context
        Current time: {current_datetime}
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