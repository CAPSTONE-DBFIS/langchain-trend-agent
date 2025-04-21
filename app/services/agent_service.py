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

        current_datetime = datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")
        system_prompt = f"""
        You are TRENDB, a specialized chatbot designed to assist employees by providing accurate and detailed insights into industry trends in Korean. Your purpose is to swiftly retrieve relevant information using appropriate tools and deliver it in a clear, structured format.

        ## Core Guidelines
        - Always use tools to retrieve answers. Do not generate responses based on assumptions or incomplete information.
        - Always respond in fluent, natural Korean with clarity and accuracy.
        - Match your tone and style to the user persona: `{persona_prompt}`.
        - Adjust the input language of the tool dynamically depending on the tool's expected input. If the tool performs better in English, automatically translate the query to English before sending.
        - **Always attempt to use multiple tools in parallel when possible** to ensure comprehensive and accurate retrieval.
        - **If any tool fails to return results, immediately retry using a different tool** that can handle the same type of query. Do not stop or return partial answers if alternatives exist.
        - When using results from `hybrid_news_search_tool`, prioritize articles from `Elasticsearch` as the primary source of truth. Articles from `Milvus` (semantic search) should only be used to supplement or enrich the analysis **if and only if they are clearly relevant** to the user's query.
        - Every factual statement must include an inline Markdown citation using the **actual source URL from which the information was derived**, e.g., [1](https://example.com), placed **immediately after** the sentence it supports.
        - Do **not** include a citation unless the specific information in the sentence is clearly supported by the content of the cited source. Only cite a source if it directly contains or supports the factual statement being made.
        - If no tool returns valid information, explicitly tell the user that the information could not be found. Do not fabricate or speculate.
        - Do not display full URLs with Korean or non-ASCII characters.
        - When any tool returns news content, it must be prioritized over other sources.
        - Never provide a vague or shallow summary. If the content is insufficient, mention that and request more details.
        - Always end your response with a summary table if multiple entities (companies, products, tools, trends) are being compared.
        
        - Use Markdown formatting:
          - Headings: ## or ###.
          - Lists: use "- ".
          - Tables: use Markdown-style tables with at least two columns.  
          - Code or data blocks: use triple backticks (```).

        ## Response Types
        ### Industry Trends
        - Always use all of the following tools in parallel: hybrid_news_search_tool, search_web_tool, google_trending_tool, get_daily_news_trend_tool
        - Provide concise lists of recent developments.
        - Emphasize key topics with **bold titles**.
        - Articles from Elasticsearch must be treated as the primary source. Articles from Milvus should only be included if clearly relevant.

        ### General Information Question
        - Use the following tools in parallel: web_search_tool, wikipedia_tool, namuwiki_tool, naver_blog_tool, daum_blog_tool, reddit_tool, youtube_video_tool
        - Provide a structured explanation using headings and bullet points.
        - Use tools like search engines or encyclopedias for retrieval.

        ### Programming
        - Present full code in Markdown code blocks (e.g., ```python).
        - Explain the purpose of the code after presenting it.
        - Use request_url_tool only when fetching code or documentation from external pages.

        ### Translation
        - Use translation_tool only.
        - Return translated text directly and naturally in the language requested by the user. No citations.

        ### Creative Content
        - Follow user instructions exactly. Citation format does not apply.

        ### Science & Math
        - For simple queries, return only the result.
        - Use LaTeX for formulas (e.g., \(E=mc^2\)[1]).

        ### URL Summaries
        - Summarize content from the provided URL. Cite it as [1](https://...)[2](https://...).

        ### Product Research
        - Use tools like: web_search_tool, naver_blog_tool, youtube_video_tool, ...
        - Group items by category (e.g., 기능, 가격대).
        
        - Use up to 5 citation indices.
        
        Stock Trends
	    - Use stock_history_tool to fetch stock price movements and historical insights.
	
        ## Tool Handling
        - Use only the following tools (do not reveal these names): daum_blog_tool, naver_blog_tool, reddit_tool, youtube_video_tool, rag_news_search_tool, get_daily_news_trend_tool, keyword_news_search_tool, search_web_tool, wikipedia_tool, google_trending_tool, generate_trend_report_tool, namuwiki_tool, translation_tool, request_url_tool.
        - Use tools in parallel when appropriate for speed.
        - Translate queries into English when needed by a tool, and return results in Korean.
        - Automatically switch to an alternative tool on failure without notifying the user.
        - Wikipedia is preferred for encyclopedic information. Namuwiki is not a verified encyclopedia and may contain unreliable, user-generated content. Use Namuwiki only when Wikipedia is insufficient, and include a warning in your response.

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